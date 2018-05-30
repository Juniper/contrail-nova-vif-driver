# Derived from:
#   github.com/openstack/nova/blob/stable/queens/nova/network/linux_net.py
# Under the Apache Licence, Version 2.0. Please see there for the original
# copyright details.
#
# Copyright (c) 2011 X.commerce, a business unit of eBay Inc.
# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Implements network management commands using linux utilities."""

import os

from oslo_concurrency import processutils
from oslo_log import log as logging
from oslo_utils import excutils
from vif_plug_vrouter import privsep

LOG = logging.getLogger(__name__)


def device_exists(device):
    """Returns True if a netdev exists"""
    return os.path.exists('/sys/class/net/%s' % device)


@privsep.vif_plug.entrypoint
def create_tap_dev(dev, mac_address=None, multiqueue=False):
    """Create a TAP device, falling back to older methods"""
    if not device_exists(dev):
        try:
            # First, try with 'ip'
            cmd = ('ip', 'tuntap', 'add', dev, 'mode', 'tap')
            if multiqueue:
                cmd = cmd + ('multi_queue', )
            processutils.execute(*cmd, run_as_root=True,
                                 check_exit_code=[0, 2, 254])
        except processutils.ProcessExecutionError:
            if multiqueue:
                LOG.warning(
                    'Failed to create a tap device with ip tuntap. '
                    'tunctl does not support creation of multi-queue '
                    'enabled devices, skipping fallback.')
                raise

            # Second option: tunctl
            processutils.execute('tunctl', '-b', '-t', dev, run_as_root=True)
        if mac_address:
            processutils.execute('ip', 'link', 'set', dev, 'address',
                                 mac_address, run_as_root=True,
                                 check_exit_code=[0, 2, 254])
        processutils.execute('ip', 'link', 'set', dev, 'up', run_as_root=True,
                             check_exit_code=[0, 2, 254])


@privsep.vif_plug.entrypoint
def remove_tap_dev(dev):
    """Remove TAP device"""
    if device_exists(dev):
        try:
            processutils.execute('ip', 'link', 'delete', dev, run_as_root=True,
                                 check_exit_code=[0, 2, 254])
            LOG.debug("Net device removed: '%s'", dev)
        except processutils.ProcessExecutionError:
            with excutils.save_and_reraise_exception():
                LOG.error("Failed removing net device: '%s'", dev)
