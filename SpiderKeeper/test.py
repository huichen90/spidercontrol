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
print(datetime.datetime.date())