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

"""
DailyTimedRotatingFileHandler module. Log file name format: <name>.YYYYMMDD.log

"""

import logging
import datetime
import os

class DailyTimedRotatingFileHandler(logging.FileHandler):
    def __init__(self, filename, mode='a', encoding=None, delay=False):
        self._filename_without_date=filename+".{0:d}{1:02d}{2:02d}.log"
        self._next_rotate_at=None
        self._calc_next_file_name()
        logging.FileHandler.__init__(self, self._filename_with_date, mode, encoding, delay)

    def _calc_next_file_name(self):
        now_datetime=datetime.datetime.now()
        if self._next_rotate_at is not None and now_datetime<self._next_rotate_at:
            return 0
        self._filename_with_date=self._filename_without_date.format(now_datetime.year,now_datetime.month,now_datetime.day)
        self._next_rotate_at=datetime.datetime.combine(now_datetime.date()+datetime.timedelta(1),datetime.time())
        return 1

    def emit(self, record):
        try:
            if self._calc_next_file_name():
                if self.stream:
                    self.stream.close()
                    self.stream = None
                self.baseFilename = os.path.abspath(self._filename_with_date)
                self.stream = self._open()
            logging.FileHandler.emit(self, record)
        except (KeyboardInterrupt, SystemExit): #pragma: no cover
            raise
        except:
            self.handleError(record)
