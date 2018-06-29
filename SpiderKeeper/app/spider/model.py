import datetime
import json

from sqlalchemy import desc
from SpiderKeeper.app import db, Base


class Project(Base):
    __tablename__ = 'projects'
    '''创建的工程表'''
    project_name = db.Column(db.String(50))

    @classmethod
    def load_project(cls, project_list):   # 添加工程
        for project in project_list:
            existed_project = cls.query.filter_by(project_name=project.project_name).first()
            if not existed_project:
                db.session.add(project)
                db.session.commit()

    @classmethod
    def find_project_by_id(cls, project_id):   # 查询工程
        return Project.query.filter_by(id=project_id).first()

    def to_dict(self):
        return {
            "project_id": self.id,
            "project_name": self.project_name
        }


class SpiderInstance(Base):
    __tablename__ = 'spiders'
    '''爬虫表'''
    spider_name = db.Column(db.String(100))
    project_id = db.Column(db.INTEGER, nullable=False, index=True)

    @classmethod
    def update_spider_instances(cls, project_id, spider_instance_list):
        for spider_instance in spider_instance_list:
            existed_spider_instance = cls.query.filter_by(project_id=project_id,
                                                          spider_name=spider_instance.spider_name).first()
            if not existed_spider_instance:
                db.session.add(spider_instance)
                db.session.commit()

        for spider in cls.query.filter_by(project_id=project_id).all():
            existed_spider = any(
                spider.spider_name == s.spider_name
                for s in spider_instance_list
            )
            if not existed_spider:
                db.session.delete(spider)
                db.session.commit()

    @classmethod
    def list_spider_by_project_id(cls, project_id):
        return cls.query.filter_by(project_id=project_id).all()

    def to_dict(self):
        return dict(spider_instance_id=self.id,
                    spider_name=self.spider_name,
                    project_id=self.project_id)

    @classmethod
    def list_spiders(cls, project_id):
        sql_last_runtime = '''
            select * from (select a.spider_name,b.date_created from job_instance as a
                left join job_execution as b
                on a.id = b.job_instance_id
                order by b.date_created desc) as c
                group by c.spider_name
            '''
        sql_avg_runtime = '''
            select a.spider_name,avg(end_time-start_time) from job_instance as a
                left join job_execution as b
                on a.id = b.job_instance_id
                where b.end_time is not null
                group by a.spider_name
            '''
        last_runtime_list = dict(
            (spider_name, last_run_time) for spider_name, last_run_time in db.engine.execute(sql_last_runtime))
        avg_runtime_list = dict(
            (spider_name, avg_run_time) for spider_name, avg_run_time in db.engine.execute(sql_avg_runtime))
        res = []
        for spider in cls.query.filter_by(project_id=project_id).all():
            last_runtime = last_runtime_list.get(spider.spider_name)
            res.append(dict(spider.to_dict(),
                            **{'spider_last_runtime': last_runtime if last_runtime else '-',
                               'spider_avg_runtime': avg_runtime_list.get(spider.spider_name)
                               }))
        return res


class JobPriority():
    LOW, NORMAL, HIGH, HIGHEST = range(-1, 3)


class JobRunType():
    ONETIME = '运行一次'
    PERIODIC = '持续运行'


class JobRunTime():
    LONGTIME = '长期'
    INTERVAL = '设定区间'

class UploadTimeType():
    AUTO = '任务运行周期内最新'
    INTERVAL = '设定区间'


class JobInstance(Base):
    __tablename__ = 'job_instance'
    '''爬虫任务表'''
    job_name = db.Column(db.String(50))  # 任务名称
    # spider_type = db.Column(db.String(50))  # 采集形式
    keywords = db.Column(db.String(50))     # 关键词
    project_id = db.Column(db.INTEGER, nullable=False, index=True)  # 工程id 可以用来查询目标网站（工程名可以用目标网站命名）
    spider_name = db.Column(db.String(100), nullable=False, index=True)   # 采集形式（关键词采集/板块采集）
    run_time = db.Column(db.String(20))   # 长期/设定区间

    start_date = db.Column(db.DateTime, default=db.func.current_timestamp())  # 任务开始时间
    end_date = db.Column(db.DateTime, default=db.func.current_timestamp())    # 任务结束时间
    tags = db.Column(db.Text)  # job tag(split by , )
    spider_freq = db.Column(db.Float, default=0)  # 采集频率，以天为单位，需要将其分解映射为满足cron格式需求
    run_type = db.Column(db.String(20))  # periodic/onetime
    upload_time_type = db.Column(db.String(20))  # 设置视频上传时间的方式
    upload_time_start_date = db.Column(db.DateTime, default=db.func.current_timestamp())  # 上传时间开始
    upload_time_end_date = db.Column(db.DateTime, default=db.func.current_timestamp())  # 上传时间结束
    video_time_short = db.Column(db.Integer)   # 视频最短时间
    video_time_long = db.Column(db.Integer)    # 视频最长时间
    spider_arguments = db.Column(db.Text)  # job execute arguments(split by , ex.: arg1=foo,arg2=bar)
    priority = db.Column(db.INTEGER)       # 优先级
    cron_minutes = db.Column(db.String(20), default="0")
    cron_hour = db.Column(db.String(20), default="*")
    cron_day_of_month = db.Column(db.String(20), default="*")
    cron_day_of_week = db.Column(db.String(20), default="*")
    cron_month = db.Column(db.String(20), default="*")
    enabled = db.Column(db.INTEGER, default=0)  # 0/-1   # 任务状态

    def to_dict(self):
        return {'id': self.id,
                'date_created': self.date_created.strftime('%Y-%m-%d') if self.date_created else None,
                'job_instance_id': self.id,
                'job_name': self.job_name,
                'keywords': self.keywords,
                # spider_type=self.spider_type,
                "project_id": self.project_id,
                'spider_name': self.spider_name,
                'run_time': self.run_time,
                'start_date': self.start_date.strftime('%Y-%m-%d') if self.start_date else None,
                'end_date': self.end_date.strftime('%Y-%m-%d') if self.end_date else None,
                'tags': self.tags.split(',') if self.tags else None,
                'spider_freq': self.spider_freq,
                'run_type': self.run_type,
                'upload_time_type': self.upload_time_type,
                'upload_time_start_date': self.upload_time_start_date.strftime('%Y-%m-%d') if self.upload_time_start_date else None,
                'upload_time_end_date': self.upload_time_end_date.strftime('%Y-%m-%d') if self.upload_time_end_date else None,
                'spider_arguments': self.spider_arguments,
                'video_time_short': self.video_time_short,
                'video_time_long': self.video_time_long,
                'priority': self.priority,
                # desc=self.desc,
                'cron_minutes': self.cron_minutes,
                'cron_hour': self.cron_hour,
                'cron_day_of_month': self.cron_day_of_month,
                'cron_day_of_week': self.cron_day_of_week,
                'cron_month': self.cron_month,
                'enabled': self.enabled == 0, }




    @classmethod
    def list_job_instance_by_project_id(cls, project_id):
        return cls.query.filter_by(project_id=project_id).all()

    @classmethod
    def find_job_instance_by_id(cls, job_instance_id):
        return cls.query.filter_by(id=job_instance_id).first()


class SpiderStatus():
    PENDING, RUNNING, FINISHED, CANCELED = range(4)


class JobExecution(Base):
    __tablename__ = 'job_execution'
    '''记录爬虫的执行情况'''
    project_id = db.Column(db.INTEGER, nullable=False, index=True)
    service_job_execution_id = db.Column(db.String(50), nullable=False, index=True)  # 服务器作业执行ID
    job_instance_id = db.Column(db.INTEGER, nullable=False, index=True)  # 作业实例ID
    create_time = db.Column(db.DATETIME)
    start_time = db.Column(db.DATETIME)
    end_time = db.Column(db.DATETIME)
    running_status = db.Column(db.INTEGER, default=SpiderStatus.PENDING)
    running_on = db.Column(db.Text)

    def to_dict(self):
        job_instance = JobInstance.query.filter_by(id=self.job_instance_id).first()
        return {
            'project_id': self.project_id,
            'job_execution_id': self.id,
            'job_instance_id': self.job_instance_id,
            'service_job_execution_id': self.service_job_execution_id,
            'create_time': self.create_time.strftime('%Y-%m-%d %H:%M:%S') if self.create_time else None,
            'start_time': self.start_time.strftime('%Y-%m-%d %H:%M:%S') if self.start_time else None,
            'end_time': self.end_time.strftime('%Y-%m-%d %H:%M:%S') if self.end_time else None,
            'running_status': self.running_status,
            'running_on': self.running_on,
            'job_instance': job_instance.to_dict() if job_instance else {}
        }

    @classmethod
    def find_job_by_service_id(cls, service_job_execution_id):
        return cls.query.filter_by(service_job_execution_id=service_job_execution_id).first()

    @classmethod
    def list_job_by_service_ids(cls, service_job_execution_ids):
        return cls.query.filter(cls.service_job_execution_id.in_(service_job_execution_ids)).all()

    @classmethod
    def list_uncomplete_job(cls):
        return cls.query.filter(cls.running_status != SpiderStatus.FINISHED,
                                cls.running_status != SpiderStatus.CANCELED).all()

    @classmethod
    def list_jobs(cls, project_id, each_status_limit=100):
        result = {}
        result['PENDING'] = [job_execution.to_dict() for job_execution in
                             JobExecution.query.filter_by(project_id=project_id,
                                                          running_status=SpiderStatus.PENDING).order_by(
                                 desc(JobExecution.date_modified)).limit(each_status_limit)]
        result['RUNNING'] = [job_execution.to_dict() for job_execution in
                             JobExecution.query.filter_by(project_id=project_id,
                                                          running_status=SpiderStatus.RUNNING).order_by(
                                 desc(JobExecution.date_modified)).limit(each_status_limit)]
        result['COMPLETED'] = [job_execution.to_dict() for job_execution in
                               JobExecution.query.filter(JobExecution.project_id == project_id).filter(
                                   (JobExecution.running_status == SpiderStatus.FINISHED) | (
                                       JobExecution.running_status == SpiderStatus.CANCELED)).order_by(
                                   desc(JobExecution.date_modified)).limit(each_status_limit)]
        return result

    @classmethod
    def list_run_stats_by_hours(cls, project_id):
        result = {}
        hour_keys = []
        last_time = datetime.datetime.now() - datetime.timedelta(hours=23)
        last_time = datetime.datetime(last_time.year, last_time.month, last_time.day, last_time.hour)
        for hour in range(23, -1, -1):
            time_tmp = datetime.datetime.now() - datetime.timedelta(hours=hour)
            hour_key = time_tmp.strftime('%Y-%m-%d %H:00:00')
            hour_keys.append(hour_key)
            result[hour_key] = 0  # init
        for job_execution in JobExecution.query.filter(JobExecution.project_id == project_id,
                                                       JobExecution.date_created >= last_time).all():
            hour_key = job_execution.create_time.strftime('%Y-%m-%d %H:00:00')
            result[hour_key] += 1
        return [dict(key=hour_key, value=result[hour_key]) for hour_key in hour_keys]

class Videoitems(db.Model):
    __tablename__ = 'videoitems'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(500),nullable=False)
    url = db.Column(db.String(100), nullable=False, index=True)
    keywords = db.Column(db.String(100), nullable=False)
    tags = db.Column(db.String(1000),default=[])
    video_category = db.Column(db.String(50),default="其它")
    upload_time = db.Column(db.String(50))
    spider_time = db.Column(db.String(50))
    info = db.Column(db.Text)
    site_name = db.Column(db.String(20), default="")
    video_time = db.Column(db.Integer, default=0)
    isdownload = db.Column(db.Integer, default=0)
    play_count = db.Column(db.String(20), default="0")
    task_id = db.Column(db.String(20))


class RunningJob(Base):
    __tablename__ = 'running_job'
    spider_random_id = db.Column(db.String(50),nullable=False,index=True)