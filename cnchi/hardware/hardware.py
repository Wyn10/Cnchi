#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  hardware.py
#
#  Copyright © 2013-2015 Antergos
#
#  This file is part of Cnchi.
#
#  Cnchi is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  Cnchi is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with Cnchi; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.

""" Hardware related packages installation """

import logging
import os
import subprocess

_HARDWARE_PATH = '/usr/share/cnchi/cnchi/hardware'


class Hardware(object):
    """ This is an abstract class. You need to use this as base """
    def __init__(self, class_name, class_id, vendor_id, devices, priority=-1):
        self.class_name = class_name
        self.class_id = class_id
        self.vendor_id = vendor_id
        self.devices = devices
        self.priority = priority

        self.product_id = ""

    def get_packages(self):
        """ Returns all necessary packages to install """
        raise NotImplementedError("get_packages is not implemented")

    def post_install(self, dest_dir):
        """ This method runs commands that need to be run AFTER installing the driver """
        raise NotImplementedError("post_install is not implemented")

    def pre_install(self, dest_dir):
        """ This method runs commands that need to run BEFORE installing the driver """
        pass

    def check_device(self, class_id, vendor_id, product_id):
        """ Checks if the driver supports this device """
        if not class_id == self.class_id:
            return False

        if len(self.vendor_id) > 0 and vendor_id != self.vendor_id:
            return False

        if len(self.devices) > 0 and product_id not in self.devices:
            return False

        return True

    def detect(self):
        """ Tries to guess if a device suitable for this driver is present """
        # Get PCI devices
        lines = subprocess.check_output(["lspci", "-n"]).decode().split("\n")
        for line in lines:
            if len(line) > 0:
                class_id = "0x{0}".format(line.split()[1].rstrip(":"))
                if class_id == self.class_id:
                    dev = line.split()[2].split(":")
                    vendor_id = "0x{0}".format(dev[0])
                    product_id = "0x{0}".format(dev[1])
                    if vendor_id == self.vendor_id and product_id in self.devices:
                        return True
        return False

    def is_proprietary(self):
        """ Proprietary drivers are drivers for your hardware devices
            that are not freely-available or open source, and must be
            obtained from the hardware manufacturer. """
        return False

    def is_graphic_driver(self):
        """ Tells us if this is a graphic driver or not """
        if self.class_id == "0x0300":
            return True
        else:
            return False

    def get_name(self):
        return self.class_name

    def get_priority(self):
        return self.priority

    @staticmethod
    def chroot(cmd, dest_dir, stdin=None, stdout=None):
        """ Runs command inside the chroot """
        run = ['chroot', dest_dir]

        for element in cmd:
            run.append(element)

        try:
            proc = subprocess.Popen(run,
                                    stdin=stdin,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT)
            out = proc.communicate()[0]
            logging.debug(out.decode())
        except OSError as err:
            logging.error(_("Error running command: %s"), err.strerror)

    def __str__(self):
        return "class name: {0}, class id: {1}, vendor id: {2}, product id: {3}".format(
            self.class_name,
            self.class_id,
            self.vendor_id,
            self.product_id)

    @staticmethod
    def call_script(self, script_path, dest_dir):
        if os.path.exists(path):
            cmd = [
                "/usr/bin/bash",
                script_path,
                dest_dir,
                self.class_name]
            try:
                subprocess.check_call(cmd, timeout=300)
                logging.debug(_("%s completed successfully."), script_path)
            except subprocess.CalledProcessError as process_error:
                # Even though Post-install script call has failed we will try to continue with the installation.
                logging.error(_("Error running %s script"), script_path)
                logging.error(_("Command %s failed"), process_error.cmd)
                logging.error(_("Output: %s"), process_error.output)
            except subprocess.TimeoutExpired as timeout_error:
                logging.error(timeout_error)


class HardwareInstall(object):
    """ This class checks user's hardware

    If 'use_proprietary_graphic_drivers' is True, this module will try to install the proprietary
    variants of the graphic drivers available (only if the hardware is detected).
    For non graphical drivers, the open one is always choosen as default.
    """

    def __init__(self, use_proprietary_graphic_drivers=False):
        self.use_proprietary_graphic_drivers = use_proprietary_graphic_drivers

        # All available objects
        self.all_objects = []

        # All objects that support devices found (can have more than one object for each device)
        self.objects_found = {}

        # All objects that are really used
        self.objects_used = []

        dirs = os.listdir(_HARDWARE_PATH)

        # We scan the folder for py files.
        # This is unsafe, but we don't care if somebody wants Cnchi to run code arbitrarily.
        for filename in dirs:
            if filename.endswith(".py") and "__init__" not in filename and "hardware" not in filename:
                filename = filename[:-len(".py")]
                name = ""
                try:
                    if __name__ == "__main__":
                        package = filename
                    else:
                        package = "hardware." + filename
                    name = filename.capitalize()
                    # This instruction is the same as "from package import name"
                    class_name = getattr(__import__(package, fromlist=[name]), "CLASS_NAME")
                    obj = getattr(__import__(package, fromlist=[class_name]), class_name)()
                    self.all_objects.append(obj)
                except ImportError as err:
                    logging.error(_("Error importing %s from %s : %s"), name, package, err)
                except Exception as err:
                    logging.error(_("Unexpected error importing %s: %s"), package, err)

        # Detect devices
        devices = self.get_devices()

        logging.debug(
            _("Cnchi will test %d drivers for %d hardware devices"),
            len(self.all_objects),
            len(devices))

        # Find objects that support the devices we've found.
        self.objects_found = {}
        for obj in self.all_objects:
            for device in devices:
                (class_id, vendor_id, product_id) = device
                check = obj.check_device(
                    class_id=class_id,
                    vendor_id=vendor_id,
                    product_id=product_id)
                if check:
                    if device not in self.objects_found:
                        self.objects_found[device] = [obj]
                    else:
                        self.objects_found[device].append(obj)

        self.objects_used = []
        for device in self.objects_found:
            objects = self.objects_found[device]
            objects_used = []
            if len(objects) > 1:
                # We have more than one driver for this device!
                # We'll need to choose one
                for obj in objects:
                    if not obj.is_graphic_driver():
                        # For non graphical drivers, we choose the open one as default
                        if not obj.is_proprietary():
                            objects_used.append(obj)
                    else:
                        # It's a graphic driver, we need to know which one the user wants
                        if not self.use_proprietary_graphic_drivers:
                            # OK, we choose the open one
                            if not obj.is_proprietary():
                                objects_used.append(obj)
                        else:
                            # User wants the proprietary one
                            if obj.is_proprietary():
                                objects_used.append(obj)

                if len(objects_used) > 1:
                    # We still have two or more options,
                    # let's check their priority
                    priorities = []
                    for obj in objects_used:
                        priorities.append(obj.get_priority())
                    for obj in objects_used:
                        if obj.get_priority() == max(priorities):
                            self.objects_used.append(obj)
                            break
                else:
                    self.objects_used.append(objects_used)
            else:
                # Only one option, add it (it doesn't matter if it's open or not)
                self.objects_used.append(objects[0])

    def get_devices(self):
        devices = []

        # Get PCI devices
        lines = subprocess.check_output(["lspci", "-n"]).decode().split("\n")
        for line in lines:
            if len(line) > 0:
                class_id = line.split()[1].rstrip(":")
                dev = line.split()[2].split(":")
                devices.append(("0x" + class_id, "0x" + dev[0], "0x" + dev[1]))

        # Get USB devices
        lines = subprocess.check_output(["lsusb"]).decode().split("\n")
        for line in lines:
            if len(line) > 0:
                dev = line.split()[5].split(":")
                devices.append(("0", "0x" + dev[0], "0x" + dev[1]))

        return devices

    def get_packages(self):
        """ Get pacman package list for all detected devices """
        packages = []
        for obj in self.objects_used:
            packages.extend(obj.get_packages())

        # Remove duplicates (not necessary but it's cleaner)
        packages = list(set(packages))
        return packages

    def get_found_driver_names(self):
        driver_names = []
        for obj in self.objects_used:
            driver_names.append(obj.get_name())
        return driver_names

    def pre_install(self, dest_dir):
        """ Run pre install commands for all detected devices """
        for obj in self.objects_used:
            obj.pre_install(dest_dir)

    def post_install(self, dest_dir):
        """ Run post install commands for all detected devices """
        for obj in self.objects_used:
            obj.post_install(dest_dir)


''' Test case '''
if __name__ == "__main__":
    def _(x): return x
    # hardware_install = HardwareInstall(use_proprietary_graphic_drivers=False)
    hardware_install = HardwareInstall(use_proprietary_graphic_drivers=True)
    hardware_pkgs = hardware_install.get_packages()
    print(hardware_install.get_found_driver_names())
    if len(hardware_pkgs) > 0:
        txt = " ".join(hardware_pkgs)
        print("Hardware module added these packages :")
        print(txt)

    """
    from nvidia import Nvidia
    if Nvidia().detect():
        print("Nvidia detected")
    # Nvidia().post_install("/")

    from nvidia_340xx import Nvidia_340xx
    if Nvidia_340xx().detect():
        print("Nvidia-340xx detected")

    from nvidia_304xx import Nvidia_304xx
    if Nvidia_304xx().detect():
        print("nvidia-304xx detected")

    from catalyst import Catalyst
    if Catalyst().detect():
        print("Catalyst detected")
    """
