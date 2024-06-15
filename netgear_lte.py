# -*- coding:utf-8 -*-

# Collectd-netgearlte - Collectd plugin for Netgear LTE modems
# Copyleft 2024 - Nicolas AGIUS <nicolas.agius@lps-it.fr>

###########################################################################
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###########################################################################

# Depends on
# pip install requests beautifulsoup4

import collectd
import base64
import requests
from bs4 import BeautifulSoup

# Global variables
VERBOSE_LOGGING = False
IP = None
PASSWORD = None
SESSION = None

# LTE Bands data (European Union)
FREQUENCIES = {
    "LTE B1": 2100,
    "LTE B3": 1800,
    "LTE B7": 2600,
    "LTE B8": 900,
    "LTE B20": 800,
    "LTE B28": 700,
    "LTE B32": 1500,
    "LTE B38": 2600,
    "LTE B40": 2300,
}

# Netgear related methods
#########################

# Netgear URL templates
TOKEN_URL = "http://%s/sess_cd_tmp?op=%%2F&oq="
LOGIN_URL = "http://%s/Forms/config"
DATA_URL = "http://%s/model.json"

def login(session, ip, password):
    def get_token():
        response = session.get(TOKEN_URL % ip)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        for form in soup.find_all('form'):
            token_field = form.find('input', {'name': 'token'})
            if token_field:
                return token_field.get('value')

        raise Exception("token not found")

    login_data = {
            "ok_redirect": "/model.json",
            "err_redirect": "/not-found.html",
            "token": get_token(),
            "session.password": password,
            }

    response = session.post(LOGIN_URL % ip, data=login_data)
    if response.status_code == 404:
        raise Exception("login failed, check password")

    response.raise_for_status()

    return response.json()

def get_json(session, ip):
    response = session.get(DATA_URL % ip)
    response.raise_for_status()

    return response.json()

def get_data(session, ip, password):
    data=get_json(session, ip)
    if data['session']['userRole'] != 'Admin':
        collectd.info("netgear_lte plugin: Session closed, reconnecting...")
        data=login(session, ip, password)

    return data

def get_frequency_for_band(band):
    if band in FREQUENCIES:
        return FREQUENCIES[band]
    else:
        return 0

# Collectd interface
####################

def log_verbose(msg):
    if not VERBOSE_LOGGING:
        return
    collectd.info('netgear_lte plugin [verbose]: %s' % msg)

def configure_callback(conf):
    global VERBOSE_LOGGING, IP, PASSWORD
    for c in conf.children:
        if c.key == 'Verbose':
            VERBOSE_LOGGING = bool(c.values[0])
        elif c.key == 'Ip':
            IP = c.values[0]
        elif c.key == 'Password64':
            PASSWORD = base64.b64decode(c.values[0]).decode('utf-8')
        else:
            collectd.warning ('netgear_lte plugin: Unknown config key: %s.' % c.key)

def init_callback():
    global SESSION

    log_verbose('init callback called')
    if not IP:
        collectd.error("IP is not defined")
        raise Exception("IP is not defined")

    SESSION=requests.Session()

def dispatch_value(value, name, type):
    dispatch_values([value], name, type)

def dispatch_values(values, name, type):
    log_verbose('Sending values: %s=%s' % (name, values))
    val = collectd.Values(plugin='netgear_lte')
    val.plugin_instance = "netgearlte0"   # TODO manage multiple devices
    val.type = type
    val.type_instance = name
    val.values = values
    val.dispatch()

def read_callback():
    log_verbose('Read callback called')

    data=get_data(SESSION, IP, PASSWORD)

    # Network traffic
    dispatch_values([data['wwan']['dataTransferred']['rxb'], data['wwan']['dataTransferred']['txb']], 'wan', 'if_octets')

    # Signal status
    dispatch_value(1 if data['wwan']['connection'] == 'Connected' else 0, 'connected', 'gauge')
    dispatch_value(data['wwanadv']['radioQuality'], 'radio_quality', 'gauge')
    dispatch_value(get_frequency_for_band(data['wwanadv']['curBand']), 'band', 'gauge')
    dispatch_value(data['wwan']['signalStrength']['rsrp'], 'RSRP', 'gauge')
    dispatch_value(data['wwan']['signalStrength']['rsrq'], 'RSRQ', 'gauge')


collectd.register_config(configure_callback)
collectd.register_init(init_callback)
collectd.register_read(read_callback)

# vim: ts=4:sw=4:ai
