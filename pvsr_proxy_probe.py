#!/usr/bin/env python3

#
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
#
# mPlane Protocol Reference Implementation
# Information Model and Element Registry
#
# (c) 2013-2014 mPlane Consortium (http://www.ict-mplane.eu)
#               Author: Balazs Szabo <balazs.szabo@netvisor.hu>
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU Lesser General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program.  If not, see <http://www.gnu.org/licenses/>.
#

import sys
import logging
import logging.config
import os.path
import pvsr_soap_client
import pvsr_proxy_service

import re
import mplane.httpsrv
import mplane.scheduler
import mplane.model
import tornado.web
import tornado.ioloop
import json

import pdb

def die(msg):
    logging.critical(msg)
    exit(1)

def read_config_json():
    global config
    
    try:
        if len(sys.argv) >= 2:
            config_file_name = sys.argv[1]
        else:
            config_file_name = __file__.replace('.py','.cfg')

        config_file = open(config_file_name,'r')
        config = json.load(config_file)
        config_file.close()
    except FileNotFoundError:
        die("Configuration file {0} cannot be found".format(config_file_name))
    except ValueError as e:
        config_file.close()
        die("Configuration file {0} cannot be parsed: {1}".format(config_file_name, e))
    
def parse_logging_section():
    if "logging" in config:
        if "config_file" in config["logging"]:
            if os.path.isfile(config["logging"]["config_file"]):
                logging.config.fileConfig(config["logging"]["config_file"])
            else:
                die("The logging configuration file {0} cannot be found".format(config["logging"]["config_file"]))
        else:
            try:
                logging.basicConfig(**config["logging"])
            except configparser.Error as e:
                logging.critical("Error in the [logging] section in {0}:".format(config_file_name))
                die(e)
            except ValueError as e:
                logging.critical("Error in the [logging] section in {0}:".format(config_file_name))
                die(e)

def parse_soap_section():
    logging.info("parse_soap_section")
    
    if "soap" not in config:
        die("Missing section 'soap' in the configuration file")
    
    if "user" not in config["soap"]:
        die("Missing parameter 'user' in section 'soap' in the configuration file")
        
    if "password" not in config["soap"]:
        die("Missing parameter 'password' in section 'soap' in the configuration file")
        
    if "url" in config["soap"]:
        pvsr_url=config["soap"]["url"]
    else:
        pvsr_url="http://localhost:8082/"
    logging.info("Using PVSR at {0}".format(pvsr_url))
        
    if "wsdl_url" in config["soap"]:
        wsdl_url=config["soap"]["wsdl_url"]
    else:
        wsdl_url=("file:///"+re.sub(r'^(.*[\\/])[^\\/]+$',r'\1'+"PVSR.wsdl",os.path.abspath(__file__))).replace('\\','/')
    logging.info("Using WSDL at {0}".format(wsdl_url))
    
    global pvsr

    try:
        pvsr=pvsr_soap_client.PvsrSoapClient(pvsr_url,config["soap"]["user"],config["soap"]["password"],wsdl_url)
    except Exception as e:
        die(e)

def parse_measurements_section():
    logging.info("parse_soap_section")
    
    if "measurements" not in config:
        die("Missing section 'measurements' in the configuration file")
    
    if len(config["measurements"])==0:
        die("Empty section 'measurements' in the configuration file")

    global pvsr_meas_types
    
    pvsr_meas_types={}
    
    for name in sorted(config["measurements"].keys()):
        meas=config["measurements"][name]
        
        if "equipment" in meas:
            logging.info("Using equipment {0}".format(meas["equipment"]))
        else:
            die("Missing parameter 'equipment' in measurements section {0}".format(name))
        
        if "types" not in meas:
            die("Missing section 'types' in measurements section {0}".format(name))
        if len(meas["types"])==0:
            die("Empty section 'types' in measurements section {0}".format(name))
        
        meas["collector_type"]=None
        meas["name"]=name
        
        for k in meas["types"].keys():
            if "first" not in meas["types"][k] and "second" not in meas["types"][k]:
                die("Measurement section is missing either first or second, section {0} type {1}".format(name,k))
            if len(k)>1 and k[0:1]=='#':
                new_collector_type=k[1:2]
            else:
                new_collector_type="S"
            if meas["collector_type"] is None:
                meas["collector_type"]=new_collector_type
            elif meas["collector_type"] != new_collector_type:
                die("Only one collector type is allowed in one measurements section, section {0}".format(name))
            pvsr_meas_types[k] = None

def preload_soap_data():
    logging.info("preload_soap_data")
    
    if "default_site" not in config:
        config["default_site"]="mPlane"
    logging.info("Default site is {0}".format(config["default_site"]))
    
    if "delete_created_measurements" not in config:
        config["delete_created_measurements"]=True
    if config["delete_created_measurements"]:
        logging.info("Newly created measurements WILL BE deleted")
    else:
        logging.info("Newly created measurements WILL NOT BE deleted")
    
    
    if "pvsr_default_conf_check_cycle" not in config:
        config["pvsr_default_conf_check_cycle"]=300
    logging.info("Assuming {0} PVSR configuration check cycle".format(config["pvsr_default_conf_check_cycle"]))
    
    logging.info("query measurement types")
    try:
        for type in pvsr_meas_types:
            logging.debug("get {0}".format(type))
            meas_type=pvsr.create_pvsr_object("MeasurementType")
            meas_type.Type=type
            res=pvsr.listMeasurementTypes(meas_type)
            if len(res)==1:
                pvsr_meas_types[type]=res[0]
            else:
                die("Unknown measurement type {0}".format(type))
    except Exception as e:
        die("Cannot establish initial PVSR connection: {0}".format(e))
    
if __name__ == "__main__":
    read_config_json()
   
    parse_logging_section()
    
    parse_measurements_section()
    
    parse_soap_section()
    
    preload_soap_data()
    
    mplane.model.initialize_registry()
    scheduler = mplane.scheduler.Scheduler()

    for name in sorted(config["measurements"].keys()):
        meas=config["measurements"][name]
        scheduler.add_service(
            pvsr_proxy_service.PvsrService(
                meas
                ,mplane.model.VERB_QUERY
                ,pvsr
                ,config["default_site"]
                ,config["delete_created_measurements"]
                ,config["pvsr_default_conf_check_cycle"]
                ,pvsr_meas_types
            )
        )
        scheduler.add_service(
            pvsr_proxy_service.PvsrService(
                meas
                ,mplane.model.VERB_MEASURE
                ,pvsr
                ,config["default_site"]
                ,config["delete_created_measurements"]
                ,config["pvsr_default_conf_check_cycle"]
                ,pvsr_meas_types
            )
        )

    logging.info("starting service")

    mplane.httpsrv.runloop(scheduler)
