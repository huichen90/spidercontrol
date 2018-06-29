import time


def dts2ts(datestr):
    '''
    datestring translate to timestamp
    '''
    timeArray = time.strptime(datestr, "%Y-%m-%d")
    timeStamp = int(time.mktime(timeArray))
    return timeStamp

def ts2dts(timeStamp):

    '''timestamp translate to datestring'''
    timeArray = time.localtime(timeStamp)
    datestr = time.strftime("%Y-%m-%d", timeArray)
    return datestr