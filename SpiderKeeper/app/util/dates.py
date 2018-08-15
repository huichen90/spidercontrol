import datetime
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


if __name__ == '__main__':
    ee = ts2dts(1534052846)
    aa = datetime.datetime.utcnow()
    ts = int(time.time()) - 3600 * 24 * 1
    print(ts2dts(1534228873), ts)
    print(ts2dts(1534003200))
    print(ts2dts(1534315273))

    # print(aa)
    # print(dts2ts(aa))