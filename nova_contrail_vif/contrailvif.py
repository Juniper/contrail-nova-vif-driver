# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2013 Juniper Networks, Inc. All rights reserved.
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

import gettext
import threading
import time

gettext.install('contrail_vif')

from oslo.config import cfg

from nova.network import linux_net
# Default to _ as this does not work in havana
try:
    from nova.openstack.common.gettextutils import _LE
except:
    _LE = _
from nova.openstack.common import log as logging
from nova.openstack.common import loopingcall
from nova.openstack.common import processutils
from nova.virt.libvirt import designer
from nova.virt.libvirt.vif import LibvirtBaseVIFDriver

from contrail_vrouter_api.vrouter_api import ContrailVRouterApi

from thrift.Thrift import TApplicationException

LOG = logging.getLogger(__name__)


class VRouterVIFDriver(LibvirtBaseVIFDriver):
    """VIF driver for VRouter when running Neutron."""
    
    PORT_TYPE = 'NovaVMPort'

    def __init__(self, get_connection):
        super(VRouterVIFDriver, self).__init__(get_connection)
        self._vrouter_client = ContrailVRouterApi()
        timer = loopingcall.FixedIntervalLoopingCall(self._keep_alive)
        timer.start(interval=2)

    def _keep_alive(self):
        self._vrouter_client.periodic_connection_check()

    @staticmethod
    def _get_br_name(dev):
        """Returns the bridge name for a tap device.
        This is lxc related stuff. To work around the fact, that libvirt does
        not support direct passthrough of devices to LXC."""
        return 'br%s' % dev[3:]

    def _create_bridge(self, dev, instance):
        """Creating a bridge and returning its name"""
        br_name = self._get_br_name(dev)

        try:
            linux_net.LinuxBridgeInterfaceDriver.ensure_bridge(br_name, dev)
            linux_net._execute('ip', 'link', 'set', br_name, 'promisc', 'on',
                               run_as_root=True)
        except processutils.ProcessExecutionError:
            LOG.exception(_LE("Failed while plugging vif"), instance=instance)

        return br_name

    def get_config(self, instance, vif, image_meta, inst_type):
        conf = super(VRouterVIFDriver, self).get_config(instance, vif,
                                                        image_meta, inst_type)
        dev = self.get_vif_devname(vif)
        if cfg.CONF.libvirt_type == 'lxc':
            # for lxc we need to pass a bridge to libvirt
            br_name = self._get_br_name(dev)
            designer.set_vif_host_backend_bridge_config(conf, br_name)
        else:
            designer.set_vif_host_backend_ethernet_config(conf, dev)
        designer.set_vif_bandwidth_config(conf, inst_type)

        return conf

    def plug(self, instance, vif):
        dev = self.get_vif_devname(vif)

        try:
            linux_net.create_tap_dev(dev)
        except processutils.ProcessExecutionError:
            LOG.exception(_LE("Failed while plugging vif"), instance=instance)
        if cfg.CONF.libvirt_type == 'lxc':
            dev = self._create_bridge(dev, instance)

        kwargs = {
            'ip_address': vif['network']['subnets'][0]['ips'][0]['address'],
            'vn_id': vif['network']['id'],
            'display_name': instance['display_name'],
            'hostname': instance['hostname'],
            'host': instance['host'],
            'vm_project_id': instance['project_id'],
            'port_type': self.PORT_TYPE,
        }
        try:
            result = self._vrouter_client.add_port(instance['uuid'],
                                                   vif['id'],
                                                   dev,
                                                   vif['address'],
                                                   **kwargs)
            if not result:
                LOG.exception(_LE("Failed while plugging vif"),
                              instance=instance)
        except TApplicationException:
            LOG.exception(_LE("Failed while plugging vif"), instance=instance)

    def unplug(self, instance, vif):
        dev = self.get_vif_devname(vif)

        try:
            self._vrouter_client.delete_port(vif['id'])
	    #delegate the deletion of tap device to a deffered thread
            worker_thread = threading.Thread(target=self.delete_device, \
		name='contrailvif', args=(dev,))
	    worker_thread.start()
        except (TApplicationException, processutils.ProcessExecutionError,\
	    RuntimeError):
            LOG.exception(_LE("Failed while unplugging vif"),
                          instance=instance)

    def delete_device(self, dev):
        time.sleep(2)
        LOG.debug(dev)
        if cfg.CONF.libvirt_type == 'lxc':
            linux_net.LinuxBridgeInterfaceDriver.remove_bridge(
                    self._get_br_name(dev))
        linux_net.delete_net_dev(dev)

