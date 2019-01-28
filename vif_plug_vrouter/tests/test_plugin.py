# Derived from github.com:Juniper/nova/tests/unit/virt/libvirt/test_vif.py
# licenced under the Apache Licence, Version 2.0. Please see there for the
# copyright details.
#
# Copyright 2016 Semihalf.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.


import os
import sys

import contextlib
import mock
import six
import testtools

from oslo_concurrency import processutils

from os_vif import objects

from vif_plug_vrouter import privsep
from vif_plug_vrouter import vrouter
from vif_plug_vrouter.vrouter import VHOSTUSER_MODE_CLIENT
from vif_plug_vrouter.vrouter import VHOSTUSER_MODE_SERVER


sys.modules['oslo_config'] = mock.Mock()


objects.register_all()


if six.PY2:
    nested = contextlib.nested
else:
    @contextlib.contextmanager
    def nested(*contexts):
        with contextlib.ExitStack() as stack:
            yield [stack.enter_context(c) for c in contexts]


def _vhu_mode_to_int(mode):
    return VHOSTUSER_MODE_SERVER if mode == 'server' \
        else VHOSTUSER_MODE_CLIENT


class PluginTest(testtools.TestCase):

    def __init__(self, *args, **kwargs):
        super(PluginTest, self).__init__(*args, **kwargs)
        privsep.vif_plug.set_client_mode(False)
        self.test_env = dict(os.environ)
        self.test_env['PATH'] = self.test_env['PATH'] + ':/opt/plugin/bin'
        if hasattr(objects.vif, 'DatapathOffloadRepresentor'):
            # os-vif supports offloads
            self.offload_subnet_bridge_4 = objects.subnet.Subnet(
                cidr='101.168.1.0/24',
                dns=['8.8.8.8'],
                gateway='101.168.1.1',
                dhcp_server='191.168.1.1'
            )
            self.offload_subnet_bridge_6 = objects.subnet.Subnet(
                cidr='101:1db9::/64',
                gateway='101:1db9::1'
            )
            self.offload_subnets = objects.subnet.SubnetList(
                objects=[self.offload_subnet_bridge_4,
                         self.offload_subnet_bridge_6]
            )
            self.offload_network = objects.network.Network(
                id='f0ff5378-7367-4451-9202-829b068143f3',
                bridge='br0',
                subnets=self.offload_subnets,
                vlan=99)
            self.vif_vrouter_direct = objects.vif.VIFHostDevice(
                id="dc065497-3c8d-4f44-8fb4-e1d33c16a536",
                address="22:52:25:62:e2:aa",
                dev_type=objects.fields.VIFHostDeviceDevType.ETHERNET,
                dev_address="0000:08:08.5",
                port_profile=objects.vif.VIFPortProfileBase(
                    datapath_offload=objects.vif.DatapathOffloadRepresentor(
                        representor_name="nicdc065497-3c",
                        representor_address="0000:08:08.5")
                    ),
                vif_name="nicdc065497-3c",
                network=self.offload_network)
            self.vif_vrouter_forwarder = objects.vif.VIFVHostUser(
                id="dc065497-3c8d-4f44-8fb4-e1d33c16a536",
                address="22:52:25:62:e2:aa",
                vif_name="nicdc065497-3c",
                path='/fake/socket',
                mode='client',
                port_profile=objects.vif.VIFPortProfileBase(
                    datapath_offload=objects.vif.DatapathOffloadRepresentor(
                        representor_address="0000:08:08.5",
                        representor_name="nicdc065497-3c")
                    ),
                network=self.offload_network)

    subnet_bridge_4 = objects.subnet.Subnet(
        cidr='101.168.1.0/24',
        dns=['8.8.8.8'],
        gateway='101.168.1.1',
        dhcp_server='191.168.1.1'
    )

    subnet_bridge_6 = objects.subnet.Subnet(
        cidr='101:1db9::/64',
        gateway='101:1db9::1'
    )

    subnets = objects.subnet.SubnetList(
        objects=[subnet_bridge_4,
                 subnet_bridge_6]
    )

    network_vrouter = objects.network.Network(
        id='f0ff5378-7367-4451-9202-829b068143f3',
        bridge='br0',
        subnets=subnets,
        vlan=99)

    vif_vrouter_vhostuser = objects.vif.VIFVHostUser(
        id='40137937-43c3-47d9-be65-d3a13041c5cf',
        address='ca:fe:de:ad:be:ef',
        network=network_vrouter,
        path='/var/run/openvswitch/vhub679325f-ca',
        mode='client',
        vif_name='tapXXX'
    )

    vif_vrouter_vhostuser_no_path = objects.vif.VIFVHostUser(
        id='f4454d55-ebb1-4bc8-9f92-7ade5e6a3350',
        address='ca:fe:de:ad:be:ef',
        network=network_vrouter,
        mode='client',
        vif_name='tapXXX'
    )

    vif_vrouter = objects.vif.VIFGeneric(
        id='a909a869-e967-4c5f-8f54-fbd57dc798a9',
        address='ca:fe:de:ad:be:ef',
        network=network_vrouter,
        vif_name='tap-xxx-yyy-zzz'
    )

    instance = objects.instance_info.InstanceInfo(
        name='Instance 1',
        uuid='f0000000-0000-0000-0000-000000000001',
        project_id='1'
    )

    def test_vrouter_vhostuser_plug(self):
        calls = {
            '_vrouter_port_add': [mock.call(self.instance,
                                  self.vif_vrouter_vhostuser)]
        }
        with mock.patch.object(vrouter.VrouterPlugin,
                               '_vrouter_port_add') as port_add:
            plugin = vrouter.VrouterPlugin.load("vrouter")
            plugin.plug(self.vif_vrouter_vhostuser, self.instance)

            port_add.assert_has_calls(calls['_vrouter_port_add'])

    def test_vrouter_vhostuser_unplug(self):
        calls = {
            '_vrouter_port_delete': [mock.call(self.instance,
                                     self.vif_vrouter_vhostuser)]
        }
        with mock.patch.object(vrouter.VrouterPlugin,
                               '_vrouter_port_delete') as delete_port:
            plugin = vrouter.VrouterPlugin.load("vrouter")
            plugin.unplug(self.vif_vrouter_vhostuser, self.instance)

            delete_port.assert_has_calls(calls['_vrouter_port_delete'])

    def test_vrouter_vhostuser_port_add(self):
        ip_addr = '0.0.0.0'
        ip6_addr = None
        ptype = 'NovaVMPort'
        vtype = 'VhostUser'
        cmd_args = ("--oper=add",
                    "--uuid=%s" % self.vif_vrouter_vhostuser.id,
                    "--instance_uuid=%s" % self.instance.uuid,
                    "--vn_uuid=%s" % self.vif_vrouter_vhostuser.network.id,
                    "--vm_project_uuid=%s" % self.instance.project_id,
                    "--ip_address=%s" % ip_addr,
                    "--ipv6_address=%s" % ip6_addr,
                    "--vm_name=%s" % self.instance.name,
                    "--mac=%s" % self.vif_vrouter_vhostuser.address,
                    "--tap_name=%s" % self.vif_vrouter_vhostuser.vif_name,
                    "--port_type=%s" % ptype,
                    "--vif_type=%s" % vtype,
                    "--vhostuser_socket=%s" % self.vif_vrouter_vhostuser.path,
                    "--vhostuser_mode=%s" %
                    _vhu_mode_to_int(self.vif_vrouter_vhostuser.mode),
                    "--tx_vlan_id=%d" % -1,
                    "--rx_vlan_id=%d" % -1)
        calls = {
            'execute': [mock.call('vrouter-port-control', *cmd_args,
                                  env_variables=self.test_env)]
        }

        with mock.patch.object(processutils, 'execute') as execute_cmd:
            vrouter.VrouterPlugin._vrouter_port_add(
                self.instance, self.vif_vrouter_vhostuser
            )

            execute_cmd.assert_has_calls(calls['execute'])

    def test_vrouter_vhostuser_port_delete(self):
        calls = {
            'execute': [
                mock.call(
                    'vrouter-port-control',
                    '--oper=delete',
                    '--uuid=%s' % self.vif_vrouter_vhostuser.id,
                    env_variables=self.test_env
                )
            ]
        }

        with mock.patch.object(processutils, 'execute') as execute_cmd:
            vrouter.VrouterPlugin._vrouter_port_delete(
                    self.instance, self.vif_vrouter_vhostuser
            )

            execute_cmd.assert_has_calls(calls['execute'])

    def test_unplug_vrouter_direct(self):
        if not hasattr(objects.vif, 'DatapathOffloadRepresentor'):
            # This version of os-vif does not support offloads
            return
        with mock.patch.object(processutils, 'execute') as execute:
            plugin = vrouter.VrouterPlugin.load("vrouter")
            plugin.unplug(self.vif_vrouter_direct, self.instance)
            execute.assert_has_calls([
                mock.call(
                    'vrouter-port-control',
                    '--oper=delete',
                    '--uuid=dc065497-3c8d-4f44-8fb4-e1d33c16a536',
                    '--vnic_type=direct',
                    '--pci_dev=0000:08:08.5',
                    env_variables=self.test_env
                ),
            ])

    def test_plug_vrouter_direct(self):
        if not hasattr(objects.vif, 'DatapathOffloadRepresentor'):
            # This version of os-vif does not support offloads
            return
        instance = mock.Mock()
        instance.name = 'instance-name'
        instance.uuid = '46a4308b-e75a-4f90-a34a-650c86ca18b2'
        instance.project_id = 'b168ea26fa0c49c1a84e1566d9565fa5'
        with mock.patch.object(processutils, 'execute') as execute:
            plugin = vrouter.VrouterPlugin.load("vrouter")
            plugin.plug(self.vif_vrouter_direct, instance)
            execute.assert_has_calls([
                mock.call(
                    'vrouter-port-control',
                    '--oper=add',
                    '--uuid=dc065497-3c8d-4f44-8fb4-e1d33c16a536',
                    '--instance_uuid=46a4308b-e75a-4f90-a34a-650c86ca18b2',
                    '--vn_uuid=f0ff5378-7367-4451-9202-829b068143f3',
                    '--vm_project_uuid=b168ea26fa0c49c1a84e1566d9565fa5',
                    '--ip_address=0.0.0.0',
                    '--ipv6_address=None',
                    '--vm_name=instance-name',
                    '--mac=22:52:25:62:e2:aa',
                    '--tap_name=nicdc065497-3c',
                    '--port_type=NovaVMPort',
                    '--vnic_type=direct',
                    '--pci_dev=0000:08:08.5',
                    '--tx_vlan_id=-1',
                    '--rx_vlan_id=-1',
                    env_variables=self.test_env)
                ],
            )

    def test_unplug_vrouter_forwarder(self):
        if not hasattr(objects.vif, 'DatapathOffloadRepresentor'):
            # This version of os-vif does not support offloads
            return
        with mock.patch.object(processutils, 'execute') as execute:
            plugin = vrouter.VrouterPlugin.load("vrouter")
            plugin.unplug(self.vif_vrouter_forwarder, self.instance)
            execute.assert_called_once_with(
                'vrouter-port-control',
                '--oper=delete',
                '--uuid=dc065497-3c8d-4f44-8fb4-e1d33c16a536',
                '--tap_name=nicdc065497-3c',
                '--vnic_type=virtio-forwarder',
                '--pci_dev=0000:08:08.5',
                '--vhostuser_socket=/fake/socket',
                '--vhostuser_mode=0',
                env_variables=self.test_env
            )

    def test_plug_vrouter_forwarder(self):
        if not hasattr(objects.vif, 'DatapathOffloadRepresentor'):
            # This version of os-vif does not support offloads
            return
        instance = mock.Mock()
        instance.name = 'instance-name'
        instance.uuid = '46a4308b-e75a-4f90-a34a-650c86ca18b2'
        instance.project_id = 'b168ea26fa0c49c1a84e1566d9565fa5'
        with mock.patch.object(processutils, 'execute') as execute:
            plugin = vrouter.VrouterPlugin.load("vrouter")
            plugin.plug(self.vif_vrouter_forwarder, instance)
            execute.assert_has_calls([
                mock.call(
                    'vrouter-port-control',
                    '--oper=add',
                    '--uuid=dc065497-3c8d-4f44-8fb4-e1d33c16a536',
                    '--instance_uuid=46a4308b-e75a-4f90-a34a-650c86ca18b2',
                    '--vn_uuid=f0ff5378-7367-4451-9202-829b068143f3',
                    '--vm_project_uuid=b168ea26fa0c49c1a84e1566d9565fa5',
                    '--ip_address=0.0.0.0',
                    '--ipv6_address=None',
                    '--vm_name=instance-name',
                    '--mac=22:52:25:62:e2:aa',
                    '--tap_name=nicdc065497-3c',
                    '--port_type=NovaVMPort',
                    '--vif_type=VhostUser',
                    '--vnic_type=virtio-forwarder',
                    '--pci_dev=0000:08:08.5',
                    '--vhostuser_socket=/fake/socket',
                    '--vhostuser_mode=0',
                    '--tx_vlan_id=-1',
                    '--rx_vlan_id=-1',
                    env_variables=self.test_env)
                ]
            )

    def test_unplug_vrouter(self):
        with mock.patch.object(processutils, 'execute') as execute:
            plugin = vrouter.VrouterPlugin.load("vrouter")
            plugin.unplug(self.vif_vrouter, self.instance)
            execute.assert_has_calls([
                mock.call(
                    'vrouter-port-control',
                    '--oper=delete',
                    '--uuid=a909a869-e967-4c5f-8f54-fbd57dc798a9',
                    env_variables=self.test_env
                ),
            ])

    def test_plug_vrouter(self):
        instance = mock.Mock()
        instance.name = 'instance-name'
        instance.uuid = '46a4308b-e75a-4f90-a34a-650c86ca18b2'
        instance.project_id = 'b168ea26fa0c49c1a84e1566d9565fa5'
        with mock.patch.object(processutils, 'execute') as execute:
            plugin = vrouter.VrouterPlugin.load("vrouter")
            plugin.plug(self.vif_vrouter, instance)
            execute.assert_has_calls([
                mock.call(
                    'vrouter-port-control',
                    '--oper=add',
                    '--uuid=a909a869-e967-4c5f-8f54-fbd57dc798a9',
                    '--instance_uuid=46a4308b-e75a-4f90-a34a-650c86ca18b2',
                    '--vn_uuid=f0ff5378-7367-4451-9202-829b068143f3',
                    '--vm_project_uuid=b168ea26fa0c49c1a84e1566d9565fa5',
                    '--ip_address=0.0.0.0',
                    '--ipv6_address=None',
                    '--vm_name=instance-name',
                    '--mac=ca:fe:de:ad:be:ef',
                    '--tap_name=tap-xxx-yyy-zzz',
                    '--port_type=NovaVMPort',
                    '--tx_vlan_id=-1',
                    '--rx_vlan_id=-1',
                    env_variables=self.test_env)
                ],
            )

    def test_unplug_vrouter_vhostuser(self):
        with mock.patch.object(processutils, 'execute') as execute:
            plugin = vrouter.VrouterPlugin.load("vrouter")
            plugin.unplug(self.vif_vrouter_vhostuser, self.instance)
            execute.assert_called_once_with(
                'vrouter-port-control',
                '--oper=delete',
                '--uuid=40137937-43c3-47d9-be65-d3a13041c5cf',
                env_variables=self.test_env
            )

    def test_plug_vrouter_vhostuser(self):
        instance = mock.Mock()
        instance.name = 'instance-name'
        instance.uuid = '46a4308b-e75a-4f90-a34a-650c86ca18b2'
        instance.project_id = 'b168ea26fa0c49c1a84e1566d9565fa5'
        with mock.patch.object(processutils, 'execute') as execute:
            plugin = vrouter.VrouterPlugin.load("vrouter")
            plugin.plug(self.vif_vrouter_vhostuser, instance)
            execute.assert_has_calls([
                mock.call(
                    'vrouter-port-control',
                    '--oper=add',
                    '--uuid=40137937-43c3-47d9-be65-d3a13041c5cf',
                    '--instance_uuid=46a4308b-e75a-4f90-a34a-650c86ca18b2',
                    '--vn_uuid=f0ff5378-7367-4451-9202-829b068143f3',
                    '--vm_project_uuid=b168ea26fa0c49c1a84e1566d9565fa5',
                    '--ip_address=0.0.0.0',
                    '--ipv6_address=None',
                    '--vm_name=instance-name',
                    '--mac=ca:fe:de:ad:be:ef',
                    '--tap_name=tapXXX',
                    '--port_type=NovaVMPort',
                    '--vif_type=VhostUser',
                    '--vhostuser_socket=/var/run/openvswitch/vhub679325f-ca',
                    '--vhostuser_mode=0',
                    '--tx_vlan_id=-1',
                    '--rx_vlan_id=-1',
                    env_variables=self.test_env)
                ]
            )
