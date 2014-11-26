#
# Copyright (c) 2013 Juniper Networks, Inc. All rights reserved.
#

# -*- mode: python; -*-

env = DefaultEnvironment().Clone()

sources = [
    'setup.py',
    'requirements.txt',
    'nova_contrail_vif/__init__.py',
    'nova_contrail_vif/contrailvif.py',
]

sdist_gen = env.Command('dist', sources,
                        'cd ' + Dir('.').path + ' && python setup.py sdist')
env.Default(sdist_gen)
env.Alias('nova-contrail-vif', sdist_gen)

if 'install' in BUILD_TARGETS:
    cmd = 'cd ' + Dir('.').path + ' && python setup.py install %s'
    env.Alias('install',
              env.Command(None, sources, cmd % env['PYTHON_INSTALL_OPT']))

env.Alias('compute-node-install', sdist_gen)
cmd = 'cd ' + Dir('.').path + ' && python setup.py install %s'
env.Alias('compute-node-install',
           env.Command(None, sources, cmd % env['PYTHON_INSTALL_OPT']))
