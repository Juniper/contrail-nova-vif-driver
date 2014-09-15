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

    def get_config(self, instance, vif, image_meta, inst_type):
        conf = super(VRouterVIFDriver, self).get_config(instance, vif,
                                                        image_meta, inst_type)
        dev = self.get_vif_devname(vif)
        designer.set_vif_host_backend_ethernet_config(conf, dev)
        designer.set_vif_bandwidth_config(conf, inst_type)

        return conf

    def plug(self, instance, vif):
        dev = self.get_vif_devname(vif)

        try:
            linux_net.create_tap_dev(dev)
        except processutils.ProcessExecutionError:
            LOG.exception(_LE("Failed while plugging vif"), instance=instance)

        ipv4_address = None
        ipv6_address = None
        subnets = vif['network']['subnets']
        for subnet in subnets:
            ips = subnet['ips'][0]
            if (ips['version'] == 4):
                if ips['address'] is not None:
                    ipv4_address = ips['address']
            if (ips['version'] == 6):
                if ips['address'] is not None:
                    ipv6_address = ips['address']
      
        kwargs = {
            'ip_address': ipv4_address,
            'vn_id': vif['network']['id'],
            'display_name': instance['display_name'],
            'hostname': instance['hostname'],
            'host': instance['host'],
            'vm_project_id': instance['project_id'],
            'port_type': self.PORT_TYPE,
            'ip6_address': ipv6_address,
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
            linux_net.delete_net_dev(dev)
        except (TApplicationException, processutils.ProcessExecutionError):
            LOG.exception(_LE("Failed while unplugging vif"),
                          instance=instance)
