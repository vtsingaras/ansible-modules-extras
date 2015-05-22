#!/usr/bin/python
#
# Copyright (c) 2015 Vyronas Tsingaras <vtsingaras@it.auth.gr, Aristotle University of Thessaloniki
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

DOCUMENTATION = '''
---
module: dhcpd
short_description: Simple module that sets/reads entries from an ISC-DHCP server
description:
    - Module that interfaces with an ISC-DHCP server using OMAPI to add/remove host objects or lookup lease objects
version_added: "2.0"
author: Vyronas Tsingaras
requirements:
    - This module requires the Python pypureomapi module
    - You should have configured your dhcp server to enable OMAPI
options:
    state:
        description:
            - Desired add/remove operation. 'present' for adding a new host entry and 'absent' fo tremoving one by it's IP or Hardware address.
        required: false
        default: present
        choices: [present, absent]
    gather_facts:
        description:
            - If set to true query the DHCP server for the specified IP or Hardware address and return the lease-pair as an Ansible fact.
        required: false
        default: null
    mac_address:
        description:
            - Target MAC address, if ommited ip_address must be supplied
        required: false
        default: null
    ip_address:
        description:
            - Target IPv4 address, if ommited mac_address must be supplied
        required: false
        default: null
    server:
        description:
            - IP or hostname of DHCP server
        required: true
        default: null
    port:
        description:
            - OMAPI DHCP port
        required: false
        default: 7911
    key_name:
        description:
            - OMAPI key name as specified in the omapi-key directive in dhcpd.conf
        required: false
        default: null
    key_secret:
        description:
            - base64-encoded OMAPI key secret as specified in the "key $KEYNAME" stanza in dhcpd.conf
        required: false
        default: null
'''

EXAMPLES = '''
# Add a new host object entry in dhcpd.leases
- dhcpd: state=present ip_address=10.0.0.10 mac_address=13:37:be:ef:00:00 server=dhcp.example.org key_name=omapi_key key_secret="base64encodedsecretgoeshere"
# Remove a host object entry in dhcpd.leases by its mac address
- dhcpd: state=absent mac_address=13:37:be:ef:00:00 server=dhcp.example.org
# Lookup a lease by its IP address, its ip and mac addresses will be registered as dhcp_mac and dhcp_ip
- dhcpd: gather_facts=true ip_address=10.0.0.10 server=dhcp.example.org
'''

import json

try:
    import pypureomapi
    HAVE_PYPUREOMAPI=True
except ImportError:
    HAVE_PYPUREOMAPI=False

def main():
    module = AnsibleModule(
        argument_spec = dict(
            state   = dict(default='present', choices=['present', 'absent']),
            gather_facts = dict(default=None, choices=BOOLEANS),
            mac_address = dict(default=None, type='str'),
            ip_address = dict(default=None, type='str'),
            server = dict(required=True, type='str'),
            port = dict(default=7911, type='int'),
            key_name = dict(default=None, type='str'),
            key_secret = dict(default=None, type='str')
        ),
        required_together = [
                                ['key_name', 'key_secret']
                            ],
        required_one_of = [
                                ['mac_address', 'ip_address'].
                                ['gather_facts', 'state']
                          ],
        supports_check_mode=False
    )

    if not HAVE_PYPUREOMAPI:
        module.fail_json(msg="The pypureomapi python library is required")

    if (module.params['state'] is None) or (module.params['state'] == 'absent'):
        if not ( (module.params['mac_address'] is not None) ^ (module.params['ip_address'] is not None) ):
            module.fail_json(msg="state=absent or gather_facts=true require exactly either one Hardware or one IP address")
    if module.params['state'] == 'present':
        if not ( (module.params['mac_address'] is not None) and (module.params['ip_address'] is not None) ):
            module.fail_json(msg="state=present requires both an IP and a Hardware address")

    try:
        dhcpd_omapi = pypureomapi.Omapi(module.params['server'], module.params['port'], module.params['key_name'], module.params['key_secret'])
    except pypureomapi.OmapiError:
        module.fail_json(msg="Error connecting to dhcp server")

    #if state is none then query dhcpd and return as facts
    if module.boolean(module.params['gather_facts']):
        ansible_facts_dict = {
            "changed" : False,
            "ansible_facts": {
                }
        }
        if module.params['ip_address'] is not None:
            try:
                mac = dhcpd_omapi.lookup_mac(module.params['ip_address'])
                ansible_facts_dict['ansible_facts']['dhcp_ip'] = module.params['ip_address']
                ansible_facts_dict['ansible_facts']['dhcp_mac'] = mac
                print json.dumps(ansible_facts_dict)
                return 0
            except pypureomapi.OmapiErrorNotFound:
                module.fail_json(msg="Entry not found")
        else:
            try:
                ip = dhcpd_omapi.lookup_ip(module.params['mac_address'])
                ansible_facts_dict['ansible_facts']['dhcp_ip'] = ip
                ansible_facts_dict['ansible_facts']['dhcp_mac'] = module.params['mac_address']
                print json.dumps(ansible_facts_dict)
                return 0
            except pypureomapi.OmapiErrorNotFound:
                module.fail_json(msg="Entry not found")

    #insert new host entry
    if module.params['state'] == 'present':
        try:
            dhcpd_omapi.add_host(module.params['ip_address'], module.params['mac_address'])
            module.exit_json(changed=True)
        except pypureomapi.OmapiError:
            module.fail_json(msg="Could not add entry")

    #remove host entry by mac or ip
    if module.params['state'] == 'absent':
        if module.params['mac_address'] is not None:
            mac = module.params['mac_address']
        elif module.params['ip_address'] is not None:
            try:
                mac = dhcpd_omapi.lookup_mac(module.params['ip_address'])
            except pypureomapi.OmapiErrorNotFound:
                module.fail_json(msg="Could not lookup Hardware address for leased IP address")
        else:
            module.fail_json(msg="Removing a host entry requires exactly either one Hardware or one IP address")
        try:
            dhcpd_omapi.del_host(mac)
            module.exit_json(changed=True)
        except pypureomapi.OmapiErrorNotFound:
            module.exit_json(changed=False)
        except pypureomapi.OmapiError:
            module.fail_json(msg="Could not remove entry")

    module.fail_json(msg="No action specified!")

# import module snippets
from ansible.module_utils.basic import *
main()


# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
