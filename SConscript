#
# Copyright (c) 2013 Juniper Networks, Inc. All rights reserved.
#

# -*- mode: python; -*-

env = DefaultEnvironment().Clone()

sources = [
    'MANIFEST.in',
    'setup.py',
    'tox.ini',
    'requirements.txt',
    'test-requirements.txt',
    'nova_contrail_vif/__init__.py',
    'nova_contrail_vif/contrailvif.py',
    'vif_plug_vrouter/i18n.py',
    'vif_plug_vrouter/tests/test_plugin.py',
    'vif_plug_vrouter/tests/__init__.py',
    'vif_plug_vrouter/privsep.py',
    'vif_plug_vrouter/exception.py',
    'vif_plug_vrouter/__init__.py',
    'vif_plug_vrouter/vrouter.py',
]

sdist_gen = env.Command('dist', sources,
                        'cd ' + Dir('.').path + ' && python setup.py sdist')
env.Default(sdist_gen)
env.Alias('nova-contrail-vif', sdist_gen)

if 'install' in BUILD_TARGETS:
    cmd = 'cd ' + Dir('.').path + ' && python setup.py install %s'
    env.Alias('install',
              env.Command(None, sources, cmd % env['PYTHON_INSTALL_OPT']))
