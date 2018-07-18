import datetime
import threading
import time

from SpiderKeeper.app.util.http import request_get

from SpiderKeeper.app import scheduler, app, agent, db
from SpiderKeeper.app.spider.model import Project, JobInstance, SpiderInstance, WebMonitor, WebMonitorLog


def sync_job_execution_status_job():
    """
    sync job execution running status
    :return:
    """
    for project in Project.query.all():
        agent.sync_job_status(project)
    app.logger.debug('[sync_job_execution_status]')

def sync_job_instance_status():
    """
    sync job instance status
    :return:
    """
    for job_instance in JobInstance.query.all():
        if job_instance.end_date < datetime.datetime.now() and job_instance.run_time == '设定区间':
            job_instance.enabled = 1
            db.session.commit()
    app.logger.debug('[sync_job_instance_status]')


def sync_spiders():
    """
    sync spiders
    :return:
    """
    for project in Project.query.all():
        spider_instance_list = agent.get_spider_list(project)
        SpiderInstance.update_spider_instances(project.id, spider_instance_list)
    app.logger.debug('[sync_spiders]')


def run_spider_job(job_instance_id):
    """
    run spider by scheduler
    :param job_instance_id:
    :return:
    """
    try:
        job_instance = JobInstance.find_job_instance_by_id(job_instance_id)
        agent.start_spider(job_instance)
        app.logger.info('[run_spider_job][project:%s][spider_name:%s][job_instance_id:%s]' % (
            job_instance.project_id, job_instance.spider_name, job_instance.id))
    except Exception as e:
        app.logger.error('[run_spider_job] ' + str(e))


def reload_runnable_spider_job_execution():
    """
    add periodic job to scheduler
    :return:
    """
    running_job_ids = set([job.id for job in scheduler.get_jobs()])             # 正在运行的任务id
    app.logger.debug('[running_job_ids] %s' % ','.join(running_job_ids))
    available_job_ids = set()                                                   # 可运行的任务id
    # add new job to schedule
    for job_instance in JobInstance.query.filter_by(enabled=0, run_type="持续运行").all():
        job_id = "spider_job_%s:%s" % (job_instance.id, int(time.mktime(job_instance.date_modified.timetuple())))
        available_job_ids.add(job_id)
        if job_id not in running_job_ids:
            scheduler.add_job(run_spider_job,
                              args=(job_instance.id,),
                              trigger='cron',
                              id=job_id,
                              minute=job_instance.cron_minutes,
                              hour=job_instance.cron_hour,
                              day=job_instance.cron_day_of_month,
                              day_of_week=job_instance.cron_day_of_week,
                              month=job_instance.cron_month,
                              second=0,
                              max_instances=999,
                              misfire_grace_time=60 * 60,
                              coalesce=True,
                              start_date=job_instance.start_date.strftime('%Y-%m-%d'),
                              end_date=job_instance.end_date.strftime('%Y-%m-%d'))
            app.logger.info('[load_spider_job][project:%s][spider_name:%s][job_instance_id:%s][job_id:%s]' % (
                job_instance.project_id, job_instance.spider_name, job_instance.id, job_id))
        if job_instance.run_type == '运行一次':
            job_instance.enabled = -1
            db.session.commit()

    # remove invalid jobs
    for invalid_job_id in filter(lambda job_id: job_id.startswith("spider_job_"),
                                 running_job_ids.difference(available_job_ids)):
        scheduler.remove_job(invalid_job_id)
        app.logger.info('[drop_spider_job][job_id:%s]' % invalid_job_id)

def web_monitor():
    """
    Website monitoring
    :param :
    :return:
    """
    target_webs = WebMonitor.query.all()
    for target_web in target_webs:
        web_url = target_web.web_url
        web_id = target_web.id
        target_web_monitor_log = WebMonitorLog()
        target_web_monitor_log.web_id = web_id
        target_web_monitor_log.monitor_date = datetime.datetime.now()
        target_web.end_date = target_web_monitor_log.monitor_date         # 添加最后一次监测时间
        rst = request_get(url=web_url, retry_times=2)
        if rst is None:
            target_web_monitor_log.status = '断开'
            target_web.status = '断开'
            target_web.disconnect_time = target_web_monitor_log.monitor_date   # 添加上一次断开的时间
            target_web.disconnect_num = target_web.disconnect_num + 1          # 断开次数加一
            db.session.add(target_web_monitor_log)
            db.session.commit()
        else:
            target_web.status = '正常'
            db.session.add(target_web_monitor_log)
            db.session.commit()
