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

import mplane.model
import mplane.scheduler
import pdb
import logging
import time
import datetime

class PvsrService(mplane.scheduler.Service):
    valid_periods=frozenset([15,30,60,300,600,900,1800,3600])
    def __init__(self, meas, verb,pvsr, default_site,delete_created_measurements,pvsr_default_conf_check_cycle,pvsr_meas_types):
        logging.info("adding capability: {0}".format(meas["name"]))
        
        self._verb=verb
        if verb==mplane.model.VERB_QUERY:
            cap = mplane.model.Capability(label=meas["name"]+"-query", when = "past ... now / 15s", verb=mplane.model.VERB_QUERY)
        elif verb==mplane.model.VERB_MEASURE:
            cap = mplane.model.Capability(label=meas["name"]+"-measure", when = "now ... future / 15s", verb=mplane.model.VERB_MEASURE)
        else:
            raise ValueError("Verb is not supported: {0}".format(verb))
        cap.add_result_column("time")
        
        self._mplane2uda={}
        self._uda_name2uda = {}
        
        self._pvsr_default_conf_check_cycle=pvsr_default_conf_check_cycle
        
        try:
            for k in sorted(meas["types"].keys()):
                if "first" in meas["types"][k]:
                    logging.debug("    result colum: {0}".format(meas["types"][k]["first"]))
                    cap.add_result_column(meas["types"][k]["first"])
                if "second" in meas["types"][k]:
                    logging.debug("    result colum: {0}".format(meas["types"][k]["second"]))
                    cap.add_result_column(meas["types"][k]["second"])
    
                if "PropertyType" in pvsr_meas_types[k]:
                    for i in range(len(pvsr_meas_types[k]["PropertyType"])):
                        self._uda_name2uda[pvsr_meas_types[k]["PropertyType"][i]["Name"]]=pvsr_meas_types[k]["PropertyType"][i]
                    
            if "index_mplane_name" in meas:
                logging.debug("    parameter: {0}".format(meas["index_mplane_name"]))
                cap.add_parameter(meas["index_mplane_name"])
                
            if "mplane_constants" in meas:
                for k,v in sorted(meas["mplane_constants"].items()):
                    logging.debug("    parameter: {0} with value {1}".format(k,v))
                    cap.add_parameter(k,v)
            
            if "uda_name2mplane_name" in meas:
                for k,v in sorted(meas["uda_name2mplane_name"].items()):
                    if k in self._uda_name2uda:
                        logging.debug("    parameter: {0}".format(v))
                        cap.add_parameter(v)
                        self._mplane2uda[v]=k
                    else:
                        logging.error("    unknown UDA: {0}".format(v))
        except Exception as e:
            logging.critical("Error during capability creation: {0}".format(e))
            raise e

        super(PvsrService, self).__init__(cap)
        
        self._pvsr = pvsr
        self._meas = meas
        self._default_site = default_site
        self._delete_created_measurements = delete_created_measurements
        self._pvsr_meas_types = pvsr_meas_types

    def run(self, spec, check_interrupt):
        logging.info("run specification {0}".format(spec))
        
        measurements=None
        res=None

        period = spec.when().period()
        if period is None:
            raise ValueError("Missing period value")
        period = int(period.total_seconds())
        if period not in PvsrService.valid_periods:
            raise ValueError("Valid periods are: {0}".format(PvsrService.valid_periods))
        
        duration = spec.when().duration()
        if duration is None:
            raise ValueError("Missing duration value")
        duration = int(duration.total_seconds())
        if duration < period:
            raise ValueError("Invalid duration")
        
        if duration % period > 0:
            raise ValueError("The duration must be whole multiple of periods")

        try:
            measurements=self._config_measurements(spec,period)
            res=self._fill_results(spec,measurements,period,duration)
        except Exception as e:
            logging.error("Error during specification {0}: {1}".format(spec,e))
            raise e
        finally:
            self._delete_measurements(measurements)
        
        logging.info("specification done {0}".format(spec))

        return res

    def _fill_results(self,spec,measurements,period,duration):
        logging.info("Fill measurements for spec {0}".format(spec))
        
        if self._verb==mplane.model.VERB_QUERY:
            (first_time,last_time) = spec.when().datetimes()
            first_time=int(first_time.replace(tzinfo=datetime.timezone.utc).timestamp() + period)
            last_time=int(last_time.replace(tzinfo=datetime.timezone.utc).timestamp())
            sleep_time = 0
        else:
            first_time = int(time.time())
            if (len(measurements[1])>0 or len(measurements[2])>0) and period<=self._pvsr_default_conf_check_cycle:
                #there are newly created or modified measurements
                first_time = first_time + self._pvsr_default_conf_check_cycle
            if first_time % period > 0:
                first_time = first_time - (first_time % period)
            last_time = first_time + int(duration / period) * period
            sleep_time = duration

        logging.debug("From: {0}, To: {1}".format(datetime.datetime.fromtimestamp(first_time),datetime.datetime.fromtimestamp(last_time)))
        
        meas_data = {}

        while True:
            logging.info("Wait {0} seconds".format(sleep_time))
            time.sleep(sleep_time)
            sleep_time = 30
            
            loaded_until=self._pvsr.getLastLoadedDataTimestamp(period)
            if int(loaded_until.timestamp())>=last_time or time.time()>last_time+period+300:
                for i in (0,1,2):
                    for j in range(len(measurements[i])):
                        self._fill_meas_result(measurements[i][j],first_time,last_time,meas_data)
                break
            else:
                logging.debug("last loaded is still {0}".format(loaded_until))
        
        res = mplane.model.Result(specification=spec)
        res.set_when(mplane.model.When(a = datetime.datetime.utcfromtimestamp(first_time+period), b = datetime.datetime.utcfromtimestamp(last_time)))
        
        tmp_time=first_time+period
        row_index=0
        while tmp_time<=last_time:
            tmp_time2 = datetime.datetime.fromtimestamp(tmp_time)
            tmp_time3 = datetime.datetime.utcfromtimestamp(tmp_time)
            res.set_result_value("time", tmp_time3, row_index)
            if tmp_time2 in meas_data:
                for mplane_name in meas_data[tmp_time2]:
                    value = str(meas_data[tmp_time2][mplane_name])
                    res.set_result_value(mplane_name, value, row_index)
            row_index+=1
            tmp_time+=period
        
        return res


    def _fill_meas_result(self,meas,from_time,to_time,meas_data):
        input=self._pvsr.create_pvsr_object("GetMeasuredValuesInput")
        input.ObjType = "Measurement"
        input.ObjId = meas.Id
        input.From = datetime.datetime.fromtimestamp(from_time)
        input.To = datetime.datetime.fromtimestamp(to_time)
        logging.info("Get values, eq: {0}, type: {1}, index: {2}, name: {3}, {4} -> {5}".format(self._meas["equipment"],meas.Type,meas.Index,meas.DescriptionToShow,input.From,input.To))
        meas_res=self._pvsr.getMeasuredValues(input)
        
        index2mplane_name={}
        multiply = None
        if "first" in self._meas["types"][meas.Type]:
            index2mplane_name[0]=self._meas["types"][meas.Type]["first"]
        if "second" in self._meas["types"][meas.Type]:
            index2mplane_name[1]=self._meas["types"][meas.Type]["second"]
        if "multiply" in self._meas["types"][meas.Type]:
            multiply=int(self._meas["types"][meas.Type]["multiply"])

        if hasattr(meas_res,"D"):
            for d in meas_res.D:
                if d.T not in meas_data:
                    meas_data[d.T]={}
                for index,mplane_name in index2mplane_name.items():
                    if index < len(d.V):
                        if multiply is not None:
                            d.V[index]*=multiply
                        meas_data[d.T][mplane_name]=d.V[index]
                    else:
                        meas_data[d.T][mplane_name]=None

    def _get_equipment(self):
        eq = self._pvsr.getEquipmentByName(self._meas["equipment"])
        if eq is None:
            site = self._pvsr.getSiteByName(self._default_site)
            if site is None:
                logging.info("Creating new default site {0}".format(self._default_site))
                site = self._pvsr.create_pvsr_object("Site")
                site.ParentId = 1
                site.Name = self._default_site
                site=self._pvsr.addSite(site)
            else:
                logging.debug("Default site ID is {0}".format(site.Id))
            
            logging.info("Creating new equipment: {0}".format(self._meas["equipment"]))
            if self._meas["collector_type"] == 'J':
                eq = self._pvsr.create_pvsr_object("JagaEquipment")
                eq.ASCII_0000_EQ_COLL_KEY = self._meas["equipment"] + "key"
            elif self._meas["collector_type"] == 'Y':
                eq = self._pvsr.create_pvsr_object("SynthTransEquipment")
            else:
                raise ValueError("The equipment does not exist in PVSR")            
            eq.Name = self._meas["equipment"]
            eq.ParentId = site.Id
            eq.CollectorType = self._meas["collector_type"]
            eq.IntervalInSec = 300
            eq.RetainRawData = 365
            eq.CollectData = "Yes"
            
            eq = self._pvsr.addEquipment(eq)
            logging.info("Added equipment {0}, id: {1}".format(self._meas["equipment"],eq.Id))
        else:
            logging.debug("Found equipment: {0}, id: {1}".format(self._meas["equipment"],eq.Id))
        return eq
        
    def _add_or_update_measurement(self,eq,meas_type,mplane_param2value,period):
        meas = self._pvsr.create_pvsr_object("Measurement")
        meas.ParentId = eq.Id
        meas.Type = meas_type
        if "index_mplane_name" in self._meas:
            if self._meas["index_mplane_name"] not in mplane_param2value:
                raise ValueError("Missing {0} value".format(self._meas["index_mplane_name"]))
            meas.Index = mplane_param2value[self._meas["index_mplane_name"]]
        else:
            meas.DescriptionToShow = self._meas["name"] + " " + self._pvsr_meas_types[meas_type]["Name"]
        
        measA = self._pvsr.listMeasurements(meas)
        if len(measA) == 0:
            if "index_mplane_name" not in self._meas:
                meas.Index = self._meas["name"]
                measA = self._pvsr.listMeasurements(meas)
        
        add2 = None
        
        if len(measA) == 0:
            #add
            if self._verb==mplane.model.VERB_QUERY:
                if "index_mplane_name" in self._meas:
                    raise ValueError("The measurement does not exists: Index={0}".format(meas.Index))
                else:
                    raise ValueError("The measurement does not exists: Name={0}".format(meas.DescriptionToShow))
            
            if "index_mplane_name" in self._meas:
                if eq.CollectorType == 'c':
                    meas.DescriptionToShow = mplane_param2value[self._meas["index_mplane_name"]] + " " + self._pvsr_meas_types[meas_type]["Name"]
                else:
                    meas.DescriptionToShow = self._meas["name"] + " " + self._pvsr_meas_types[meas_type]["Name"]
                
            if "uda_constants" in self._meas:
                for uda,value in self._meas["uda_constants"].items():
                    param=self._pvsr.create_pvsr_object("Parameter")
                    param.Name = uda
                    param.Value = value
                    meas.Parameter.append(param)

            for mplane_param,uda in self._mplane2uda.items():
                if mplane_param in mplane_param2value and mplane_param2value[mplane_param] != "":
                    param=self._pvsr.create_pvsr_object("Parameter")
                    param.Name = uda
                    param.Value = mplane_param2value[mplane_param]
                    meas.Parameter.append(param)
                elif self._uda_name2uda[uda].Required == "Yes":
                    raise ValueError("Missing required parameter: {0}".format(mplane_param))
            
            logging.info("Creating measurement, eq: {0}, type: {1}, index: {2}, name: {3}".format(eq.Name,meas.Type,meas.Index,meas.DescriptionToShow))
            
            meas.Switched = "No"
            meas.RetainRawData = 365
            meas.IntervalInSec = period
            
            add2 = 1
            meas = self._pvsr.addMeasurement(meas)
        else:
            #update
            meas = measA[0]
            logging.info("Measurement already exists: eq: {0}, type: {1}, index: {2}, name: {3}".format(eq.Name,meas.Type,meas.Index,meas.DescriptionToShow))
            
            need_mod = False
            meas_param_name2value = {}
            if hasattr(meas,"Parameter"):
                for i in range(len(meas.Parameter)):
                    meas_param_name2value[meas.Parameter[i].Name]=meas.Parameter[i].Value

            if "check_udas" in self._meas and self._meas["check_udas"] == False:
                pass
            else:
                for mplane_param,uda in self._mplane2uda.items():
                    if mplane_param in mplane_param2value and mplane_param2value[mplane_param] != "":
                        if uda not in meas_param_name2value or meas_param_name2value[uda] != mplane_param2value[mplane_param]:
                            if uda not in meas_param_name2value:
                                logging.warn("Parameter mismatch: {0}: NULL != {1}".format(uda,mplane_param2value[mplane_param]))
                            else:
                                logging.warn("Parameter mismatch: {0}: {1} != {2}".format(uda,meas_param_name2value[uda],mplane_param2value[mplane_param]))
                                index2remove=None
                                for i in range(len(meas.Parameter)):
                                    if meas.Parameter[i].Name == uda:
                                        index2remove = i
                                        break
                                del meas.Parameter[index2remove]
                            need_mod = True
                            param=self._pvsr.create_pvsr_object("Parameter")
                            param.Name = uda
                            param.Value = mplane_param2value[mplane_param]
                            meas.Parameter.append(param)
                    else:
                        if uda in meas_param_name2value:
                            index2remove=None
                            for i in range(len(meas.Parameter)):
                                if meas.Parameter[i].Name == uda:
                                    index2remove = i
                                    break
                            if index2remove is not None:
                                logging.warn("Parameter mismatch: {0}: {1} != NULL".format(uda,meas_param_name2value[uda]))
                                need_mod = True
                                del meas.Parameter[index2remove]
            
            if meas.IntervalInSec != period:
                need_mod = True
                meas.IntervalInSec = period
                logging.warn("Parameter mismatch: IntervalInSec: {0} != {1}".format(meas.IntervalInSec,period))
            
            if need_mod:
                if self._verb==mplane.model.VERB_QUERY:
                    raise ValueError("The measurement parameters do not match: Name={0}".format(meas.DescriptionToShow))
                
                logging.warn("Modifying measurement: eq: {0}, type: {1}, index: {2}, name: {3}".format(eq.Name,meas.Type,meas.Index,meas.DescriptionToShow))
                meas = self._pvsr.modMeasurement(meas)
                add2 = 2
            else:
                add2 = 0
        
        return (meas,add2)
    
    def _config_measurements(self, spec, period):
        logging.info("Config measurement for spec {0}".format(spec))
        
        eq = self._get_equipment()

        measurements=[[],[],[]]
        
        mplane_param2value={}
        for k in spec.parameter_names():
            v = spec.get_parameter_value(k)
            if isinstance(v,float):
                v = "{:.0f}".format(v)
            else:
                v = str(v)
            mplane_param2value[k] = v
        
        for meas_type in sorted(self._meas["types"].keys()):
            (meas,add2)=self._add_or_update_measurement(eq,meas_type,mplane_param2value,period)
            measurements[add2].append(meas)
        
        return measurements

    def _delete_measurements(self,measurements):
        if not self._delete_created_measurements:
            return
        if measurements is None:
            return
        if len(measurements) != 3:
            return
        if len(measurements[1]) == 0:
            return
        
        for i in range(len(measurements[1])):
            meas = measurements[1][i]
            logging.info("Delete measurement: eq: {0}, type: {1}, index: {2}, name: {3}".format(self._meas["equipment"],meas.Type,meas.Index,meas.DescriptionToShow))
            try:
                meas = self._pvsr.create_pvsr_object("Measurement")
                meas.Id = measurements[1][i].Id
                self._pvsr.delMeasurement(meas)
            except Exception as e:
                logging.error("Cannot delete measurement {0}: {1}".format(measurements[1][i],e))
            
 