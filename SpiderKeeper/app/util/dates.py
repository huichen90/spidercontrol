import time


def dts2ts(datestr):
    """
    datestring translate to timestamp
    :param datestr:
    :return: timeStamp
    """
    timeArray = time.strptime(datestr.strftime('%Y-%m-%d'), "%Y-%m-%d")
    timeStamp = int(time.mktime(timeArray))
    return timeStamp

def ts2dts(timeStamp):
    """
    timestamp translate to datestring
    :param timeStamp:
    :return: datestr
    """
    timeArray = time.localtime(timeStamp)
    datestr = time.strftime("%Y-%m-%d", timeArray)
    return datestr