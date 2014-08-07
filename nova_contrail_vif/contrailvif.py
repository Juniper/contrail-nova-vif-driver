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
from nova.openstack.common.gettextutils import _LE
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

    def __init__(self, get_connection):
        super(VRouterVIFDriver, self).__init__(get_connection)
        self._vrouter_client = ContrailVRouterApi()
        timer = loopingcall.FixedIntervalLoopingCall(
            self._vrouter_client.periodic_connection_check())
        timer.start(interval=2)

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

        port = {
            'port_id': vif['id'],
            'instance_id': instance['uuid'],
            'tap_name': dev,
            'ip_address': vif['network']['subnets'][0]['ips'][0]['address'],
            'vn_id': vif['network']['id'],
            'mac_address': vif['address'],
            'display_name': instance['display_name'],
            'hostname': instance['hostname'],
            'host': instance['host'],
            'vm_project_id': instance['project_id'],
        }
        try:
            result = self._vrouter_client.add_port(**port)
            if not result.success:
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
