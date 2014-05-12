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
