import time
import datetime

# from SpiderKeeper.app import JobInstance
#
# arguments = {}
# arguments = dict(map(lambda x: x.split("="),["lala=nihao"]))
# "lala=nihao".split("=")
# print(arguments)
# for job_instance in JobInstance.query.filter_by(enabled=0, run_type="持续运行").all():
#     print(job_instance.date_modified.timetuple())
#     print(int(time.mktime(job_instance.date_modified.timetuple())))
print(int(time.time()))
# print(datetime.datetime.date())

import threading
import time

exitFlag = 0


class myThread(threading.Thread):
    def __init__(self, threadID, name, counter):
        threading.Thread.__init__(self)
        self.threadID = threadID
        self.name = name
        self.counter = counter

    def run(self):
        print("开始线程：" + self.name)
        print_time(self.name, self.counter, 5)
        print("退出线程：" + self.name)


def print_time(threadName, delay, counter):
    while counter:
        if exitFlag:
            threadName.exit()
        time.sleep(delay)
        print("%s: %s" % (threadName, time.ctime(time.time())))
        counter -= 1


# # 创建新线程
# thread1 = myThread(1, "Thread-1", 1)
# thread2 = myThread(2, "Thread-2", 2)
#
# # 开启新线程
# thread1.start()
# thread2.start()
# thread1.join()
# thread2.join()
# print("退出主线程")
# threads = []  # 创建一个线程列表，用于存放需要执行的子线程
# t1 = threading.Thread(target=task1)  # 创建第一个子线程，子线程的任务是调用task1函数，注意函数名后不能有（）
# threads.append(t1)  # 将这个子线程添加到线程列表中
# t2 = threading.Thread(target=task2)  # 创建第二个子线程
# threads.append(t2)  # 将这个子线程添加到线程列表中
#
# for t in threads:  # 遍历线程列表
#     t.setDaemon(True)  # 将线程声明为守护线程，必须在start() 方法调用之前设置，如果不设置为守护线程程序会被无限挂起
#     t.start()  # 启动子线程
def num2time(num):
    m = num % 60
    s = num // 60 % 60
    h = num // 3600

    if m < 10:
        m = '0' + str(m)
    if s < 10:
        s = '0' + str(s)
    if h < 10:
        h = '0' + str(h)
    return str(h) + ':' + str(s) + ':' + str(m)


if __name__ == '__main__':
    print(num2time(100))
    l1 = [1, 3, 4, 5, 6]
    l1.reverse()
    l2 = l1
    print(l2)
