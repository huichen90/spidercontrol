import copy
import datetime
import os
import random
import tempfile

import flask_restful
import math
import requests
from flask import Blueprint, request, jsonify, g, make_response
from flask import abort
from flask import flash
from flask import redirect
from flask import render_template
from flask import session
from flask_restful_swagger import swagger
from werkzeug.utils import secure_filename
from flask.ext.httpauth import HTTPBasicAuth

from SpiderKeeper.app import db, api, agent, app
from SpiderKeeper.app.spider.model import JobInstance, Project, JobExecution, SpiderInstance, JobRunType, Videoitems, \
    WebMonitor, WebMonitorLog, User
from SpiderKeeper.app.util.dates import dts2ts
from SpiderKeeper.config import SERVERS

api_spider_bp = Blueprint('spider', __name__)

'''
========= api =========
'''


class UserRegister(flask_restful.Resource):
    @swagger.operation(
        summary='用户注册',
        notes='注册完成后需要从数据库激活',
        parameters=[{
            "name": "user_name",
            "description": "用户名",
            "required": True,
            "paramType": "form",
            "dataType": 'string'
        },
            {
                "name": "password",
                "description": "用户密码",
                "required": True,
                "paramType": "form",
                "dataType": 'string'
            }])
    def post(self):
        post_data = request.form
        if post_data:
            user = User()
            try:
                user.user_name = post_data['user_name']
                user.password = post_data['password']
                db.session.add(user)
                db.session.commit()
                return jsonify({'rst': '注册成功，需要从数据库激活才能使用', 'code': 201, 'user_name': user.user_name})
            except Exception as e:
                return jsonify({'rst': '注册失败，用户名已存在', 'code': 404})


auth = HTTPBasicAuth()


@auth.error_handler
def unauthorized():
    return make_response(jsonify({'error': 'Unauthorized access'}), 403)


class UserLogin(flask_restful.Resource):
    @auth.login_required
    @swagger.operation(
        summary='用户登录,获取token',
        parameters=[{
            "name": "username_or_token",
            "description": "用户名",
            "required": True,
            "paramType": "form",
            "dataType": 'string'
        },
            {
                "name": "password",
                "description": "用户密码",
                "required": False,
                "paramType": "form",
                "dataType": 'string'
            }])
    def post(self):
        token = g.user.generate_auth_token()
        return jsonify({'token': token.decode('ascii'), 'user_name': g.user.user_name})


@auth.verify_password
def verify_password(username_or_token, password):
    post_data = request.form
    if request.path == "/api/user/login":
        user = User.query.filter_by(user_name=post_data.get('username_or_token')).first()
        if not user or not user.verify_password(post_data.get('password')) or not user.confirmed:
            return False
    else:
        user = User.verify_auth_token(request.headers.get('username_or_token'))
        if not user:
            return False
    g.user = user
    return True


@app.route('/api/resource')
@auth.login_required
def get_resource():
    return jsonify({'data': 'Hello, %s!' % g.user.user_name})


class ProjectCtrl(flask_restful.Resource):
    @swagger.operation(
        summary='list projects',
        parameters=[])
    def get(self):
        return [project.to_dict() for project in Project.query.all()]

    @swagger.operation(
        summary='add project',
        parameters=[{
            "name": "project_name",
            "description": "project name",
            "required": True,
            "paramType": "form",
            "dataType": 'string'
        }])
    def post(self):
        project_name = request.form['project_name']
        project = Project()
        project.project_name = project_name
        db.session.add(project)
        db.session.commit()
        return project.to_dict()


class SpiderCtrl(flask_restful.Resource):
    @swagger.operation(
        summary='list spiders',
        parameters=[{
            "name": "project_id",
            "description": "project id",
            "required": True,
            "paramType": "path",
            "dataType": 'int'
        }])
    def get(self, project_id):
        project = Project.find_project_by_id(project_id)
        return [spider_instance.to_dict() for spider_instance in
                SpiderInstance.query.filter_by(project_id=project_id).all()]


class SpiderDetailCtrl(flask_restful.Resource):
    @swagger.operation(
        summary='spider detail',
        parameters=[{
            "name": "project_id",
            "description": "project id",
            "required": True,
            "paramType": "path",
            "dataType": 'int'
        }, {
            "name": "spider_id",
            "description": "spider instance id",
            "required": True,
            "paramType": "path",
            "dataType": 'int'
        }])
    def get(self, project_id, spider_id):
        spider_instance = SpiderInstance.query.filter_by(project_id=project_id, id=spider_id).first()
        return spider_instance.to_dict() if spider_instance else abort(404)

    @swagger.operation(
        summary='run spider',
        parameters=[{
            "name": "project_id",
            "description": "project id",
            "required": True,
            "paramType": "path",
            "dataType": 'int'
        }, {
            "name": "spider_id",
            "description": "spider instance id",
            "required": True,
            "paramType": "path",
            "dataType": 'int'
        }, {
            "name": "spider_arguments",
            "description": "spider arguments",
            "required": False,
            "paramType": "form",
            "dataType": 'string'
        }, {
            "name": "priority",
            "description": "LOW: -1, NORMAL: 0, HIGH: 1, HIGHEST: 2",
            "required": False,
            "paramType": "form",
            "dataType": 'int'
        }, {
            "name": "tags",
            "description": "spider tags",
            "required": False,
            "paramType": "form",
            "dataType": 'string'
        }, {
            "name": "desc",
            "description": "spider desc",
            "required": False,
            "paramType": "form",
            "dataType": 'string'
        }])
    def put(self, project_id, spider_id):
        spider_instance = SpiderInstance.query.filter_by(project_id=project_id, id=spider_id).first()
        if not spider_instance: abort(404)
        job_instance = JobInstance()
        job_instance.spider_name = spider_instance.spider_name
        job_instance.project_id = project_id
        job_instance.spider_arguments = request.form.get('spider_arguments')
        job_instance.desc = request.form.get('desc')
        job_instance.tags = request.form.get('tags')
        job_instance.run_type = JobRunType.ONETIME
        job_instance.priority = request.form.get('priority', 0)
        job_instance.enabled = -1
        db.session.add(job_instance)
        db.session.commit()
        agent.start_spider(job_instance)
        return True


JOB_INSTANCE_FIELDS = [column.name for column in JobInstance.__table__.columns]
JOB_INSTANCE_FIELDS.remove('id')
JOB_INSTANCE_FIELDS.remove('date_created')
JOB_INSTANCE_FIELDS.remove('date_modified')


class VideosCtrl(flask_restful.Resource):
    @auth.login_required
    @swagger.operation(
        summary='采集结果明细',
        parameters=[{
            "name": "username_or_token",
            "description": "token",
            "required": True,
            "paramType": "header",
            "dataType": 'string'
        }, {
            "name": "page",
            "description": "page 页数",
            "required": True,
            "paramType": "path",
            "dataType": 'int'
        }]
    )
    def get(self, page):
        videos = Videoitems.query.order_by(db.desc(Videoitems.id))
        web_list = []
        job_name_list = []
        for job_instance in JobInstance.query.all():
            job_name_list.append(job_instance.job_name)
        for target_web in WebMonitor.query.all():
            web_list.append(target_web.web_name)
        page = int(page)
        pagination = videos.paginate(page, per_page=10, error_out=False)
        videos = pagination.items
        video_num = pagination.total
        total_page = pagination.pages
        response = {}
        rsts = []
        for video in videos:
            rst = {
                'video_id': video.id,
                'task_id': video.task_id,
                'title': video.title,
                'spider_time': video.spider_time,
                'site_name': video.site_name,
                'job_name': JobInstance.query.filter_by(id=video.task_id).first().job_name,

            }
            rsts.append(rst)
        response['video_num'] = video_num
        response['total_page'] = total_page
        response['rsts'] = rsts
        response['web_list'] = web_list
        response['job_name_list'] = job_name_list
        response['user_name'] = g.user.user_name
        return jsonify({'rst': response, 'code': 200, })

    @auth.login_required
    @swagger.operation(
        summary='采集结果搜索',
        parameters=[{
            "name": "username_or_token",
            "description": "token",
            "required": True,
            "paramType": "header",
            "dataType": 'string'
        }, {
            "name": "spider_time_start",
            "description": "爬取视频的最早时间",
            "required": True,
            "paramType": "form",
            "dataType": 'string'
        }, {
            "name": "spider_time_end",
            "description": "爬去视频的最晚时间",
            "required": True,
            "paramType": "form",
            "dataType": 'string'
        }, {
            "name": "title",
            "description": "视频名称，实为关键字查询",
            "required": True,
            "paramType": "form",
            "dataType": 'string'
        }, {
            "name": "site_name",
            "description": "视频来源",
            "required": True,
            "paramType": "form",
            "dataType": 'string'
        }, {
            "name": "job_name",
            "description": "任务名称",
            "required": True,
            "paramType": "path",
            "dataType": 'string'
        }]
    )
    def post(self, page):

        web_list = []
        job_name_list = []
        for job_instance in JobInstance.query.all():
            job_name_list.append(job_instance.job_name)
        for target_web in WebMonitor.query.all():
            web_list.append(target_web.web_name)
        # 分页
        page = int(page)
        # 条件查询
        videos = Videoitems.query.filter_by().order_by(db.desc(Videoitems.id))
        pagination = videos.paginate(page, per_page=10, error_out=False)
        videos = pagination.items
        video_num = pagination.total
        total_page = pagination.pages
        response = {}
        rsts = []
        for video in videos:
            rst = {
                'video_id': video.id,
                'task_id': video.task_id,
                'title': video.title,
                'spider_time': video.spider_time,
                'site_name': video.site_name,
                'job_name': JobInstance.query.filter_by(id=video.task_id).first().job_name,

            }
            rsts.append(rst)
        response['video_num'] = video_num
        response['total_page'] = total_page
        response['rsts'] = rsts
        response['web_list'] = web_list
        response['job_name_list'] = job_name_list
        response['user_name'] = g.user.user_name
        return jsonify({'rst': response, 'code': 200, })


class VideoDetail(flask_restful.Resource):
    @auth.login_required
    @swagger.operation(
        summary='视频详情',
        parameters=[{
            "name": "username_or_token",
            "description": "token",
            "required": True,
            "paramType": "header",
            "dataType": 'string'
        }, {
            "name": "video_id",
            "description": "video的id",
            "required": True,
            "paramType": "path",
            "dataType": 'int',
        }, ]
    )
    def get(self, video_id):
        video = Videoitems.query.filter_by(id=video_id).first()

        rst = {
            'title': video.title,
            'spider_time': video.spider_time,
            'site_name': video.site_name,
            'job_name': JobInstance.query.filter_by(id=video.task_id).first().job_name,
            'url': video.url,
            'upload_time': video.upload_time,
            'info': video.info,
        }

        return jsonify({'rst': rst, 'code': 200, 'user_name': g.user.user_name})


class JobSCtrl(flask_restful.Resource):
    @auth.login_required
    @swagger.operation(
        summary='任务列表',
        parameters=[{
            "name": "username_or_token",
            "description": "token",
            "required": True,
            "paramType": "header",
            "dataType": 'string'
        },
        ]
    )
    def get(self):
        job_instances = JobInstance.query.order_by(db.desc(JobInstance.id)).all()
        job_instance_num = len(job_instances)
        job_instance_running = 0

        rsts = []
        for job_instance in job_instances:
            if job_instance.run_time == '长期':
                run_time = '长期'
            else:
                start_date = job_instance.start_date.strftime('%Y-%m-%d'),
                end_date = job_instance.end_date.strftime('%Y-%m-%d'),
                run_time = str(start_date[0]) + '至' + str(end_date[0])
            if job_instance.run_type == '持续运行' and job_instance.enabled == 0:
                job_status = '运行中'
                job_instance_running += 1
            elif job_instance.enabled == -1:
                job_status = '已暂停'
            else:
                job_status = '运行完成'
            rst = {
                'job_id': job_instance.id,
                'job_name': job_instance.job_name,
                'spider_type': job_instance.spider_name,
                'spider_freq': job_instance.spider_freq,
                'run_time': run_time,
                'run_times': job_instance.run_type,
                'job_status': job_status,
                'enabled': job_instance.enabled,
            }
            rsts.append(rst)
        return jsonify({'rst': rsts, 'code': 200, 'job_instance_num': job_instance_num,
                        'job_instance_running': job_instance_running, 'user_name': g.user.user_name})

    @auth.login_required
    @swagger.operation(
        summary='更改运行状态',
        notes='暂停与开启之间的切换',
        parameters=[{
            "name": "username_or_token",
            "description": "token",
            "required": True,
            "paramType": "header",
            "dataType": 'string'
        }, {
            "name": "job_id",
            "description": "job_id 任务的id",
            "required": True,
            "paramType": "form",
            "dataType": 'int',
        },
        ])
    def put(self):
        put_data = request.form
        job_instance = JobInstance.query.filter_by(id=put_data['job_id']).first()
        job_instance.enabled = -1 if job_instance.enabled == 0 else 0
        db.session.commit()
        return jsonify({'rst': '更改状态成功', 'code': 200, 'user_name': g.user.user_name})


class JobCtrl(flask_restful.Resource):
    @swagger.operation(
        summary='新增任务所需要的选项：',
        notes="目标网站--target_web "
              "服务器--servers",
    )
    def get(self):
        target_webs = Project.query.all()
        rst_list = []
        for target_web in target_webs:
            rst = {'project_id': target_web.id, 'project_name': target_web.project_name}  # 每遍历一次创建一个新的空字典，防止覆盖
            plate_name = []
            plates = SpiderInstance.query.filter_by(project_id=target_web.id).all()
            for plate in plates:
                plate_name.append(plate.spider_name)
            while '关键词采集' in plate_name:
                plate_name.remove('关键词采集')
            rst['plate_name'] = plate_name
            rst_list.append(rst)
        target_webs1 = [project.to_dict() for project in Project.query.all()]
        servers = SERVERS
        return jsonify({
            'rst': dict(spider_type=[
                {"关键词采集": {"target_web": target_webs1}},
                {"板块采集": {"target_web": rst_list}},
            ], servers=servers),
            'code': 200
        })

    @auth.login_required
    @swagger.operation(
        summary='添加新的任务',
        notes="这是用来添加任务的，现在只支持单个目标网站，多个关键字",
        parameters=[{
            "name": "username_or_token",
            "description": "token",
            "required": True,
            "paramType": "header",
            "dataType": 'string'
        }, {
            "name": "job_name",
            "description": "任务名称(20个字以内)",
            "required": True,
            "paramType": "form",
            "dataType": 'string'
        }, {
            "name": "spider_type",
            "description": "采集形式(关键词采集/板块采集)--",
            "required": True,
            "paramType": "form",
            "dataType": 'string'
        }, {
            "name": "project_id",
            "description": "目标网站（工程id 可以用来查询工程名可以用目标网站命名）",
            "required": True,
            "paramType": "form",
            "dataType": 'int'
        }, {
            "name": "keywords",
            "description": "关键字/板块名",
            "required": True,
            "paramType": "form",
            "dataType": 'string'
        }, {
            "name": "run_time",
            "description": "任务运行时间（长期/设定区间）",
            "required": True,
            "paramType": "form",
            "dataType": 'string'
        }, {
            "name": "start_date",
            "description": "任务开始时间",
            "required": False,
            "paramType": "form",
            "dataType": 'string'
        }, {
            "name": "end_date",
            "description": "任务结束时间",
            "required": False,
            "paramType": "form",
            "dataType": 'string'
        }, {
            "name": "spider_freq",
            "description": "采集频率，以天为单位，需要将其分解映射为满足cron格式需求",
            "required": True,
            "paramType": "form",
            "dataType": 'float'
        }, {
            "name": "run_type",
            "description": "持续运行/运行一次",
            "required": True,
            "paramType": "form",
            "dataType": 'string'
        }, {
            "name": "upload_time_type",
            "description": "设置视频上传时间的方式(任务运行周期内最新/设定区间)",
            "required": True,
            "paramType": "form",
            "dataType": 'string'
        }, {
            "name": "upload_time_start_date",
            "description": "最早的上传时间",
            "required": False,
            "paramType": "form",
            "dataType": 'string'
        }, {
            "name": "upload_time_end_date",
            "description": "最晚的上传时间",
            "required": False,
            "paramType": "form",
            "dataType": 'string'
        }, {
            "name": "video_time_short",
            "description": "爬去视频的最短时间",
            "required": True,
            "paramType": "form",
            "dataType": 'int'
        }, {
            "name": "video_time_long",
            "description": "爬去视频的最长时间",
            "required": True,
            "paramType": "form",
            "dataType": 'int'
        }, {
            "name": "spider_arguments",
            "description": "spider_arguments,  split by ','",
            "required": False,
            "paramType": "form",
            "dataType": 'string'
        },
            {
                "name": "daemon",
                "description": "服务器（auto或者服务器ip）",
                "required": True,
                "paramType": "form",
                "dataType": 'string'
            },
            {
                "name": "pri",
                "description": "优先级，紧急或者常规",
                "required": True,
                "paramType": "form",
                "dataType": 'string'
            }

        ])
    def post(self):
        """
        任务的添加
        :return:
        """
        post_data = request.form
        if post_data:
            job_instance = JobInstance()
            try:
                job_instance.user_id = g.user.id
                job_instance.job_name = post_data.get('job_name')
                # job_instance.spider_name = post_data['spider_name']
                job_instance.project_id = post_data['project_id']
                job_instance.run_time = post_data.get('run_time')  # 运行时间
                if job_instance.run_time != '长期':
                    job_instance.start_date = post_data.get('start_date')
                    job_instance.end_date = post_data.get('end_date')
                else:
                    job_instance.start_date = '1999-01-01'
                    job_instance.end_date = '2222-02-02'
                job_instance.spider_freq = post_data.get('spider_freq')
                job_instance.run_type = post_data.get('run_type')
                job_instance.upload_time_type = post_data.get('upload_time_type')
                if job_instance.upload_time_type == '设定区间':
                    job_instance.upload_time_start_date = post_data.get('upload_time_start_date')
                    job_instance.upload_time_end_date = post_data.get('upload_time_end_date')
                job_instance.video_time_short = post_data.get('video_time_short')
                job_instance.video_time_long = post_data.get('video_time_long')
                if post_data.get('daemon') != 'auto':
                    spider_args = []
                    if post_data.get('spider_arguments'):
                        spider_args = post_data.get('spider_arguments').split(",")
                    spider_args.append("daemon={}".format(post_data.get('daemon')))
                    job_instance.spider_arguments = ','.join(spider_args)
                # job_instance.spider_arguments = post_data.get('spider_arguments')
                job_instance.priority = post_data.get('priority', 0)
                job_instance.pri = post_data.get('pri')
                # 由于任务创建是通过 project name and spider name 来区分爬虫的
                # 当选则采集类型为关键词采集的时候，爬虫的名字为”关键词采集“，keywords为爬虫里的参数
                # 当选择采集类型为板块采集的时候，爬虫的名字为”相应的爬虫的名字“，因为是通过keywords传参，故将其设为
                job_instance.spider_type = post_data.get('spider_type')  # 采集样式
                if job_instance.spider_type == '关键词采集':
                    job_instance.spider_name = "关键词采集"
                    job_instance.keywords = post_data.get('keywords')
                    if job_instance.run_type == "持续运行":
                        # job_instance.cron_minutes = post_data.get('cron_minutes') or '0'
                        # job_instance.cron_minutes = '*/' + str(post_data.get('spider_freq'))
                        hour = random.randint(1, 14)
                        minutes = random.randint(1, 59)
                        job_instance.cron_minutes = minutes
                        job_instance.cron_hour = hour  # 添加随机的运行时间
                        # job_instance.cron_hour = post_data.get('cron_hour') or '*'
                        job_instance.cron_day_of_month = '*/' + str(post_data.get('spider_freq'))
                        job_instance.cron_day_of_month = post_data.get('cron_day_of_month') or '*'
                        job_instance.cron_day_of_week = post_data.get('cron_day_of_week') or '*'
                        job_instance.cron_month = post_data.get('cron_month') or '*'
                        db.session.add(job_instance)
                        # db.session.commit()
                        if job_instance.pri == '紧急':
                            agent.start_spider(job_instance)
                        return jsonify({'rst': '添加成功', 'code': 200, 'user_name': g.user.user_name})
                    else:
                        db.session.add(job_instance)
                        # db.session.commit()
                        if job_instance.pri == '紧急':
                            agent.start_spider(job_instance)
                        # agent.start_spider(job_instance)  # 当爬虫为单次执行时，会立刻执行
                        return jsonify({'rst': '添加成功', 'code': 200, 'user_name': g.user.user_name})
                else:
                    keywords_list = post_data.get('keywords').strip(',').split(',')
                    for keywords in keywords_list:
                        print(keywords)
                        new_job_instance = copy.deepcopy(job_instance)
                        new_job_instance.spider_name = keywords
                        if new_job_instance.run_type == "持续运行":
                            # job_instance.cron_minutes = post_data.get('cron_minutes') or '0'
                            new_job_instance.cron_minutes = '*/' + str(post_data.get('spider_freq'))
                            hour = random.randint(1, 14)
                            new_job_instance.cron_hour = hour  # 添加随机的运行时间
                            # job_instance.cron_hour = post_data.get('cron_hour') or '*'
                            # job_instance.cron_day_of_month = '*/' + str(post_data.get('spider_freq'))
                            new_job_instance.cron_day_of_month = post_data.get('cron_day_of_month') or '*'
                            new_job_instance.cron_day_of_week = post_data.get('cron_day_of_week') or '*'
                            new_job_instance.cron_month = post_data.get('cron_month') or '*'
                            db.session.add(new_job_instance)
                            # db.session.commit()
                            if job_instance.pri == '紧急':
                                agent.start_spider(new_job_instance)
                            # return jsonify({'rst': '添加成功', 'code': 200, 'user_name': g.user.user_name})
                        else:
                            db.session.add(new_job_instance)
                            # db.session.commit()
                            if job_instance.pri == '紧急':
                                agent.start_spider(new_job_instance)
                            # agent.start_spider(job_instance)  # 当爬虫为单次执行时，会立刻执行
                    db.session.commit()
                    return jsonify({'rst': '添加成功', 'code': 200, 'user_name': g.user.user_name})
            except Exception as e:
                return jsonify({'rst': e, 'code': 404, 'user_name': g.user.user_name})
        else:
            return jsonify({'rst': '添加失败，没有数据', 'code': 404, 'user_name': g.user.user_name})


class JobDetail(flask_restful.Resource):
    @auth.login_required
    @swagger.operation(
        summary='任务详情',
        parameters=[{
            "name": "job_id",
            "description": "job_id 任务的id",
            "required": True,
            "paramType": "path",
            "dataType": 'int'
        }, {
            "name": "username_or_token",
            "description": "token",
            "required": True,
            "paramType": "header",
            "dataType": 'string'
        }, ]
    )
    def get(self, job_id):
        try:
            job_instance = JobInstance.query.filter_by(id=job_id).first()
            print(job_instance.project_id)
            # print(I.split('=') for I in job_instance.spider_arguments.split(","))
            if job_instance.spider_arguments:
                daemon = dict((job_instance.spider_arguments.split("="),))['daemon']
            else:
                daemon = None
            if job_instance.run_time == '长期':
                run_time = '长期'
            else:
                start_date = job_instance.start_date.strftime('%Y-%m-%d'),
                end_date = job_instance.end_date.strftime('%Y-%m-%d'),
                print(start_date)
                run_time = str(start_date[0]) + '至' + str(end_date[0])
            if job_instance.run_type == '持续运行' and job_instance.enabled == 0:
                job_status = '运行中'
            elif job_instance.enabled == -1:
                job_status = '已暂停'
            else:
                job_status = '运行完成'
            rst = {
                'job_status': job_status,
                'job_name': job_instance.job_name,
                'spider_type': job_instance.spider_name,
                'target_web': Project.query.filter_by(id=job_instance.project_id).first().project_name,
                'spider_content': job_instance.keywords,
                'run_time': run_time,
                'spider_freq': job_instance.spider_freq,
                'run_times': job_instance.run_type,
                'video_upload_time': job_instance.upload_time_type,
                'video_time': str(job_instance.video_time_short) + '~' + str(job_instance.video_time_long),
                'enabled': job_instance.enabled,
                'server': daemon,
                'create_time': job_instance.date_created.strftime('%Y-%m-%d %H:%M:%S'),
                'update_time': job_instance.date_modified.strftime('%Y-%m-%d %H:%M:%S'),
                'creator': User.query.filter_by(id=job_instance.user_id).first().user_name,
            }
            return jsonify({'rst': rst, 'code': 200, 'user_name': g.user.user_name})

        except Exception as e:
            return jsonify({'rst': False, 'code': 404, 'error': e, 'user_name': g.user.user_name})


class JobDetailCtrl(flask_restful.Resource):
    @auth.login_required
    @swagger.operation(
        summary='修改任务',
        notes="采集形式和目标网站不可修改",
        parameters=[{
            "name": "username_or_token",
            "description": "token",
            "required": True,
            "paramType": "header",
            "dataType": 'string'
        }, {
            "name": "job_id",
            "description": "job_id 任务的id",
            "required": True,
            "paramType": "path",
            "dataType": 'int'
        }, {
            "name": "job_name",
            "description": "任务名称(20个字以内)",
            "required": False,
            "paramType": "form",
            "dataType": 'string',
        },
            # {
            #     "name": "spider_type",
            #     "description": "采集形式(关键词采集/板块采集)--",
            #     "required": False,
            #     "paramType": "form",
            #     "dataType": 'string'
            # }, {
            #     "name": "project_id",
            #     "description": "目标网站（工程id 可以用来查询工程名可以用目标网站命名）",
            #     "required": False,
            #     "paramType": "form",
            #     "dataType": 'int'
            # },
            {
                "name": "keywords",
                "description": "关键字/板块名",
                "required": False,
                "paramType": "form",
                "dataType": 'string'
            }, {
                "name": "run_time",
                "description": "任务运行时间（长期/设定区间）",
                "required": False,
                "paramType": "form",
                "dataType": 'string'
            }, {
                "name": "start_date",
                "description": "任务开始时间",
                "required": False,
                "paramType": "form",
                "dataType": 'string'
            }, {
                "name": "end_date",
                "description": "任务结束时间",
                "required": False,
                "paramType": "form",
                "dataType": 'string'
            }, {
                "name": "spider_freq",
                "description": "采集频率，以天为单位，需要将其分解映射为满足cron格式需求",
                "required": False,
                "paramType": "form",
                "dataType": 'float'
            }, {
                "name": "run_type",
                "description": "持续运行/运行一次",
                "required": False,
                "paramType": "form",
                "dataType": 'string'
            }, {
                "name": "upload_time_type",
                "description": "设置视频上传时间的方式(任务运行周期内最新/设定区间)",
                "required": False,
                "paramType": "form",
                "dataType": 'string'
            }, {
                "name": "upload_time_start_date",
                "description": "最早的上传时间",
                "required": False,
                "paramType": "form",
                "dataType": 'string'
            }, {
                "name": "upload_time_end_date",
                "description": "最晚的上传时间",
                "required": False,
                "paramType": "form",
                "dataType": 'string'
            }, {
                "name": "video_time_short",
                "description": "爬去视频的最短时间",
                "required": False,
                "paramType": "form",
                "dataType": 'int'
            }, {
                "name": "video_time_long",
                "description": "爬去视频的最长时间",
                "required": False,
                "paramType": "form",
                "dataType": 'int'
            }, {
                "name": "spider_arguments",
                "description": "spider_arguments,  split by ','",
                "required": False,
                "paramType": "form",
                "dataType": 'string'
            }, {
                "name": "daemon",
                "description": "服务器（auto或者服务器ip）",
                "required": False,
                "paramType": "form",
                "dataType": 'string'
            }, {
                "name": "pri",
                "description": "优先级，紧急或者常规",
                "required": True,
                "paramType": "form",
                "dataType": 'string'
            }
        ])
    def put(self, job_id):
        post_data = request.form
        if post_data:
            job_instance = JobInstance.query.filter_by(id=job_id).first()
            if not job_instance:
                abort(404)
            try:
                job_instance.job_name = post_data.get('job_name') or job_instance.job_name
                job_instance.spider_name = post_data['spider_name'] or job_instance.spider_name
                job_instance.project_id = post_data['project_id'] or job_instance.project_id
                job_instance.keywords = post_data.get('keywords') or job_instance.keywords
                job_instance.spider_type = post_data.get('spider_type') or job_instance.spider_type
                job_instance.run_time = post_data.get('run_time') or job_instance.run_time  # 运行时间
                if job_instance.run_time != '长期':
                    job_instance.start_date = post_data.get('start_date') or job_instance.start_date
                    job_instance.end_date = post_data.get('end_date') or job_instance.end_date
                job_instance.spider_freq = post_data.get('spider_freq') or job_instance.spider_freq
                job_instance.run_type = post_data.get('run_type') or job_instance.run_type
                job_instance.upload_time_type = post_data.get('upload_time_type') or job_instance.upload_time_type
                job_instance.upload_time_start_date = post_data.get('upload_time_start_date') \
                                                      or job_instance.upload_time_start_date
                job_instance.upload_time_end_date = post_data.get('upload_time_end_date') \
                                                    or job_instance.upload_time_end_date
                job_instance.video_time_short = post_data.get('video_time_short') or job_instance.video_time_short
                job_instance.video_time_long = post_data.get('video_time_long') or job_instance.video_time_long
                if post_data.get('daemon') != 'auto':
                    spider_args = []
                    if post_data.get('spider_arguments'):
                        spider_args = post_data.get('spider_arguments').split(",")
                    spider_args.append("daemon={}".format(post_data.get('daemon')))
                    job_instance.spider_arguments = ','.join(spider_args)
                # job_instance.spider_arguments = post_data.get('spider_arguments')
                job_instance.priority = post_data.get('priority', 0)
                job_instance.pri = post_data.get('pri')
                if job_instance.run_type == "持续运行":
                    # job_instance.cron_minutes = post_data.get('cron_minutes') or '0'
                    job_instance.cron_minutes = '*/' + str(post_data.get('spider_freq'))
                    job_instance.cron_hour = post_data.get('cron_hour') or '*'
                    # job_instance.cron_day_of_month = '*/' + str(post_data.get('spider_freq'))
                    job_instance.cron_day_of_month = post_data.get('cron_day_of_month') or '*'
                    job_instance.cron_day_of_week = post_data.get('cron_day_of_week') or '*'
                    job_instance.cron_month = post_data.get('cron_month') or '*'
                    job_instance.date_modified = datetime.datetime.now()
                    db.session.commit()
                    if job_instance.pri == '紧急':
                        agent.start_spider(job_instance)
                    return jsonify({'rst': '修改成功', 'code': 200, 'user_name': g.user.user_name})
                else:
                    job_instance.date_modified = datetime.datetime.now()
                    db.session.commit()
                    if job_instance.pri == '紧急':
                        agent.start_spider(job_instance)
                    # agent.start_spider(job_instance)
                    return jsonify({'rst': '修改成功', 'code': 200, 'user_name': g.user.user_name})
            except Exception as e:
                return jsonify({'rst': '修改失败 %s' % e, 'code': 404, 'user_name': g.user.user_name})
        else:
            return jsonify({'rst': '修改失败，没有数据', 'code': 404, 'user_name': g.user.user_name})


class JobExecutionCtrl(flask_restful.Resource):
    @auth.login_required
    @swagger.operation(
        summary='任务执行情况 ',
        parameters=[{
            "name": "username_or_token",
            "description": "token",
            "required": True,
            "paramType": "header",
            "dataType": 'string'
        }, {
            "name": "page",
            "description": "page 页数",
            "required": True,
            "paramType": "path",
            "dataType": 'int'
        }, {
            "name": "start_date",
            "description": "开始时间",
            "required": False,
            "paramType": "query",
            "dataType": 'string'
        }, {
            "name": "end_date",
            "description": "结束时间",
            "required": False,
            "paramType": "query",
            "dataType": 'string'
        }, {
            "name": "job_id",
            "description": "任务id",
            "required": False,
            "paramType": "query",
            "dataType": 'int'
        }, {
            "name": "job_status",
            "description": "任务状态",
            "required": False,
            "paramType": "query",
            "dataType": 'int'
        }, {
            "name": "running_status",
            "description": "执行情况",
            "required": False,
            "paramType": "query",
            "dataType": 'int'
        }]
    )
    def get(self, page):
        start_date = request.args.get('start_date')      # 开始时间
        end_date = request.args.get('end_date')          # 结束时间
        job_id = request.args.get('job_id')          # 任务id
        job_status = request.args.get('job_status')      # 任务状态
        running_status = request.args.get('running_status')    # 执行情况
        job_excutions = JobExecution.query.order_by(db.desc(JobExecution.id))
        if start_date:
            job_excutions = job_excutions.filter_by(JobExecution.date_created >= start_date)
        if end_date:
            job_excutions = job_excutions.filter_by(JobExecution.date_created <= end_date)
        if job_id:
            job_excutions = job_excutions.filter_by(job_instance_id=job_id)     # 任务id
        if job_status:
            job_excutions = job_excutions.filter_by(job_status=job_status)
        if running_status:
            job_excutions = job_excutions.filter_by(running_status=end_date)

        job_name_list = []
        for job_excution1 in JobExecution.query.all():
            job_id = job_excution1.job_instance_id
            job_name_list.append({'job_id': job_id,
                                  'job_name': JobInstance.query.filter_by(id=job_id).first().job_name})
        page = int(page)
        pagination = job_excutions.paginate(page, per_page=10, error_out=False)
        job_excutions = pagination.items
        job_excution_num = pagination.total
        total_page = pagination.pages
        response = {}
        rsts = []
        for job_excution in job_excutions:
            job_instance = JobInstance.query.filter_by(id=job_excution.job_instance_id).first()
            if job_instance.run_type == '持续运行' and job_instance.enabled == 0:
                job_status = '运行中'
            elif job_instance.enabled == -1:
                job_status = '已暂停'
            else:
                job_status = '运行完成'
            rst = {
                'job_id': job_excution.job_instance_id,
                'job_name': job_instance.job_name,
                'date': job_excution.start_time.strftime('%Y-%m-%d'),
                'job_status': job_status,
                'enabled': job_instance.enabled,
                'video_num': Videoitems.query.filter_by(spider_time=job_excution.start_time.strftime('%Y-%m-%d'),
                                                        task_id=job_excution.job_instance_id).count()
            }
            rsts.append(rst)
        response['job_excution_num'] = job_excution_num
        response['total_page'] = total_page
        response['rsts'] = rsts
        response['job_name_list'] = job_name_list
        response['user_name'] = g.user.user_name
        return jsonify(response)


class JobExecutionDetailCtrl(flask_restful.Resource):
    @swagger.operation(
        summary='stop job',
        notes='',
        parameters=[
            {
                "name": "project_id",
                "description": "project id",
                "required": True,
                "paramType": "path",
                "dataType": 'int'
            },
            {
                "name": "job_exec_id",
                "description": "job_execution_id",
                "required": True,
                "paramType": "path",
                "dataType": 'string'
            }
        ])
    def put(self, project_id, job_exec_id):
        job_execution = JobExecution.query.filter_by(project_id=project_id, id=job_exec_id).first()
        if job_execution:
            agent.cancel_spider(job_execution)
            return True


class WebMonitorCtrl(flask_restful.Resource):
    @auth.login_required
    @swagger.operation(
        summary='网站监测情况 ',
        parameters=[{
            "name": "page",
            "description": "page 页数",
            "required": True,
            "paramType": "path",
            "dataType": 'int'
        }, {
            "name": "username_or_token",
            "description": "token",
            "required": True,
            "paramType": "header",
            "dataType": 'string'
        }, {
            "name": "web_name",
            "description": "监控网站名称",
            "required": False,
            "paramType": "query",
            "dataType": 'string'
        }, {
            "name": "status",
            "description": "网站状态",
            "required": False,
            "paramType": "query",
            "dataType": 'string'
        }, ]
    )
    def get(self, page):
        web_name = request.args.get('web_name')
        status = request.args.get('status')
        target_web_monitors = WebMonitor.query
        if web_name:
            target_web_monitors = target_web_monitors.filter_by(web_name=web_name)
        if status:
            target_web_monitors = target_web_monitors.filter_by(status=status)
        target_web_list = []
        for target_web in WebMonitor.query.all():
            target_web_list.append({'web_id': target_web.id, 'web_name': target_web.web_name})
        page = int(page)
        pagination = target_web_monitors.paginate(page, per_page=10, error_out=False)
        target_web_monitors = pagination.items
        total_page = pagination.pages
        target_web_num = pagination.total
        response = {}
        rsts = []
        for target_web_monitor in target_web_monitors:
            rst = {
                'web_id': target_web_monitor.id,
                'web_name': target_web_monitor.web_name,
                'web_url': target_web_monitor.web_url,
                'web_status': target_web_monitor.status,
                'monitor_time': str(
                    math.ceil((dts2ts(target_web_monitor.end_date) - dts2ts(target_web_monitor.start_date))
                              / (3600 * 24))) + '天',
                'disconnected_num': target_web_monitor.disconnect_num,
                'disconnected_time': target_web_monitor.disconnect_time.strftime('%Y-%m-%d %H:%M:%S'),
            }
            rsts.append(rst)
        response['target_web_num'] = target_web_num
        response['total_page'] = total_page
        response['rsts'] = rsts
        response['target_web_list'] = target_web_list
        response['user_name'] = g.user.user_name
        return jsonify(response)


class WebMonitorDetailCtrl(flask_restful.Resource):
    @auth.login_required
    @swagger.operation(
        summary='网站监控日志 ',
        parameters=[{
            "name": "username_or_token",
            "description": "token",
            "required": True,
            "paramType": "header",
            "dataType": 'string'
        }, {
            "name": "web_id",
            "description": "web_id ",
            "required": True,
            "paramType": "path",
            "dataType": 'int'
        },
            {
                "name": "page",
                "description": "page 页数",
                "required": True,
                "paramType": "path",
                "dataType": 'int'
            }]
    )
    def get(self, web_id, page=1):
        page = int(page)
        pagination = WebMonitorLog.query.filter_by(web_id=web_id) \
            .order_by(db.desc(WebMonitorLog.id)).paginate(page, per_page=10, error_out=False)  # 分页
        target_web_monitor_logs = pagination.items
        target_web_monitor_logs_num = pagination.total
        total_page = pagination.pages

        target_web = WebMonitor.query.filter_by(id=web_id).first()

        rsts = {}
        log = []
        for target_web_monitor_log in target_web_monitor_logs:
            rst = {
                'monitor_date': target_web_monitor_log.monitor_date.strftime('%Y-%m-%d %H:%M:%S'),
                'web_name': target_web.web_name,
                'web_url': target_web.web_url,
                'web_status': target_web_monitor_log.status,
            }
            log.append(rst)
        rsts['target_web_monitor_log'] = log
        rsts['total_page'] = total_page
        rsts['total_log_num'] = target_web_monitor_logs_num
        rsts['user_name'] = g.user.user_name
        return jsonify(rsts)


# api.add_resource(ProjectCtrl, "/api/projects")
# api.add_resource(SpiderCtrl, "/api/projects/<project_id>/spiders")
# api.add_resource(SpiderDetailCtrl, "/api/projects/<project_id>/spiders/<spider_id>")
api.add_resource(UserRegister, "/api/user/register")  # 用户注册
api.add_resource(UserLogin, "/api/user/login")  # 用户登录
api.add_resource(JobCtrl, "/api/project/add_jobs")  # 新增任务
api.add_resource(JobSCtrl, "/api/joblist")  # 任务列表
api.add_resource(JobDetail, "/api/joblist/<job_id>")  # 任务详情
# api.add_resource(JobDetailCtrl, "/api/project/update_jobs/<job_id>")  # 任务更新
api.add_resource(VideosCtrl, "/api/joblist/videos/<page>")  # 视频列表
api.add_resource(VideoDetail, "/api/joblist/video_detail/<video_id>")  # 视频详情
api.add_resource(JobExecutionCtrl, "/api/job_executions/<page>")  # 任务执行列表
api.add_resource(WebMonitorCtrl, "/api/web_monitor/<page>")  # 网站监控列表
api.add_resource(WebMonitorDetailCtrl, "/api/web_monitor/<web_id>/<page>")  # 网站监控日志
# api.add_resource(JobExecutionCtrl, "/api/projects/<project_id>/jobexecs")
# api.add_resource(JobExecutionDetailCtrl, "/api/projects/<project_id>/jobexecs/<job_exec_id>")

'''
========= Router =========
'''


@app.before_request
def intercept_no_project():
    if request.path.find('/project//') > -1:
        flash("create project first")
        return redirect("/project/manage", code=302)


@app.context_processor
def inject_common():
    return dict(now=datetime.datetime.now(),
                servers=agent.servers)


@app.context_processor
def inject_project():
    project_context = {}
    project_context['project_list'] = Project.query.all()
    if project_context['project_list'] and (not session.get('project_id')):
        project = Project.query.first()
        session['project_id'] = project.id
    if session.get('project_id'):
        project_context['project'] = Project.find_project_by_id(session['project_id'])
        project_context['spider_list'] = [spider_instance.to_dict() for spider_instance in
                                          SpiderInstance.query.filter_by(project_id=session['project_id']).all()]
    else:
        project_context['project'] = {}
    return project_context


@app.context_processor
def utility_processor():
    def timedelta(end_time, start_time):
        '''

        :param end_time:
        :param start_time:
        :param unit: s m h
        :return:
        '''
        if not end_time or not start_time:
            return ''
        if type(end_time) == str:
            end_time = datetime.datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S')
        if type(start_time) == str:
            start_time = datetime.datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
        total_seconds = (end_time - start_time).total_seconds()
        return readable_time(total_seconds)

    def readable_time(total_seconds):
        if not total_seconds:
            return '-'
        if total_seconds / 60 == 0:
            return '%s s' % total_seconds
        if total_seconds / 3600 == 0:
            return '%s m' % int(total_seconds / 60)
        return '%s h %s m' % (int(total_seconds / 3600), int((total_seconds % 3600) / 60))

    return dict(timedelta=timedelta, readable_time=readable_time)


@app.route("/")
def index():
    project = Project.query.first()
    if project:
        return redirect("/project/%s/job/dashboard" % project.id, code=302)
    return redirect("/project/manage", code=302)


@app.route("/project/<project_id>")
def project_index(project_id):
    session['project_id'] = project_id
    return redirect("/project/%s/job/dashboard" % project_id, code=302)


@app.route("/project/create", methods=['post'])
def project_create():
    project_name = request.form['project_name']
    project = Project()
    project.project_name = project_name
    db.session.add(project)
    db.session.commit()
    return redirect("/project/%s/spider/deploy" % project.id, code=302)


@app.route("/project/<project_id>/delete")
def project_delete(project_id):
    project = Project.find_project_by_id(project_id)
    agent.delete_project(project)
    db.session.delete(project)
    db.session.commit()
    return redirect("/project/manage", code=302)


@app.route("/project/manage")
def project_manage():
    return render_template("project_manage.html")


@app.route("/project/<project_id>/job/dashboard")
def job_dashboard(project_id):
    return render_template("job_dashboard.html", job_status=JobExecution.list_jobs(project_id))


@app.route("/project/<project_id>/job/periodic")
def job_periodic(project_id):
    project = Project.find_project_by_id(project_id)
    job_instance_list = [job_instance.to_dict() for job_instance in
                         JobInstance.query.filter_by(run_type="持续运行", project_id=project_id).all()]
    print(job_instance_list)
    return render_template("job_periodic.html",
                           job_instance_list=job_instance_list)


@app.route("/project/<project_id>/job/add", methods=['post'])
def job_add(project_id):
    project = Project.find_project_by_id(project_id)
    job_instance = JobInstance()
    job_instance.spider_name = request.form['spider_name']
    job_instance.tags = request.form['tags']
    job_instance.job_name = request.form['job_name']
    print(request.form['startDate'])
    print(job_instance.spider_name)
    job_instance.spider_type = request.form['spider_type']
    print(job_instance.tags)
    job_instance.project_id = project_id
    job_instance.spider_arguments = request.form['spider_arguments']
    job_instance.priority = request.form.get('priority', 0)
    job_instance.run_type = request.form['run_type']
    # chose daemon manually
    if request.form['daemon'] != 'auto':
        spider_args = []
        if request.form['spider_arguments']:
            spider_args = request.form['spider_arguments'].split(",")
        spider_args.append("daemon={}".format(request.form['daemon']))
        job_instance.spider_arguments = ','.join(spider_args)
    if job_instance.run_type == JobRunType.ONETIME:
        job_instance.enabled = -1
        db.session.add(job_instance)
        db.session.commit()
        agent.start_spider(job_instance)
    if job_instance.run_type == JobRunType.PERIODIC:
        job_instance.cron_minutes = request.form.get('cron_minutes') or '0'
        job_instance.cron_hour = request.form.get('cron_hour') or '*'
        job_instance.cron_day_of_month = request.form.get('cron_day_of_month') or '*'
        job_instance.cron_day_of_week = request.form.get('cron_day_of_week') or '*'
        job_instance.cron_month = request.form.get('cron_month') or '*'
        # set cron exp manually
        if request.form.get('cron_exp'):
            job_instance.cron_minutes, job_instance.cron_hour, job_instance.cron_day_of_month, job_instance.cron_day_of_week, job_instance.cron_month = \
                request.form['cron_exp'].split(' ')
        db.session.add(job_instance)
        db.session.commit()
    return redirect(request.referrer, code=302)


@app.route("/project/<project_id>/jobexecs/<job_exec_id>/stop")
def job_stop(project_id, job_exec_id):
    job_execution = JobExecution.query.filter_by(project_id=project_id, id=job_exec_id).first()
    agent.cancel_spider(job_execution)
    return redirect(request.referrer, code=302)


@app.route("/project/<project_id>/jobexecs/<job_exec_id>/log")
def job_log(project_id, job_exec_id):
    job_execution = JobExecution.query.filter_by(project_id=project_id, id=job_exec_id).first()
    res = requests.get(agent.log_url(job_execution))
    res.encoding = 'utf8'
    raw = res.text
    return render_template("job_log.html", log_lines=raw.split('\n'))


@app.route("/project/<project_id>/job/<job_instance_id>/run")
def job_run(project_id, job_instance_id):
    job_instance = JobInstance.query.filter_by(project_id=project_id, id=job_instance_id).first()
    agent.start_spider(job_instance)
    return redirect(request.referrer, code=302)


@app.route("/project/<project_id>/job/<job_instance_id>/remove")
def job_remove(project_id, job_instance_id):
    job_instance = JobInstance.query.filter_by(project_id=project_id, id=job_instance_id).first()
    db.session.delete(job_instance)
    db.session.commit()
    return redirect(request.referrer, code=302)


@app.route("/project/<project_id>/job/<job_instance_id>/switch")
def job_switch(project_id, job_instance_id):
    job_instance = JobInstance.query.filter_by(project_id=project_id, id=job_instance_id).first()
    job_instance.enabled = -1 if job_instance.enabled == 0 else 0
    db.session.commit()
    return redirect(request.referrer, code=302)


@app.route("/project/<project_id>/spider/dashboard")
def spider_dashboard(project_id):
    spider_instance_list = SpiderInstance.list_spiders(project_id)
    return render_template("spider_dashboard.html",
                           spider_instance_list=spider_instance_list)


@app.route("/project/<project_id>/spider/deploy")
def spider_deploy(project_id):
    project = Project.find_project_by_id(project_id)
    return render_template("spider_deploy.html")


@app.route("/project/<project_id>/spider/upload", methods=['post'])
def spider_egg_upload(project_id):
    project = Project.find_project_by_id(project_id)
    if 'file' not in request.files:
        flash('No file part')
        return redirect(request.referrer)
    file = request.files['file']
    # if user does not select file, browser also
    # submit a empty part without filename
    if file.filename == '':
        flash('No selected file')
        return redirect(request.referrer)
    if file:
        filename = secure_filename(file.filename)
        dst = os.path.join(tempfile.gettempdir(), filename)
        file.save(dst)
        agent.deploy(project, dst)
        flash('deploy success!')
    return redirect(request.referrer)


@app.route("/project/<project_id>/project/stats")
def project_stats(project_id):
    project = Project.find_project_by_id(project_id)
    run_stats = JobExecution.list_run_stats_by_hours(project_id)
    return render_template("project_stats.html", run_stats=run_stats)


@app.route("/project/<project_id>/server/stats")
def service_stats(project_id):
    project = Project.find_project_by_id(project_id)
    run_stats = JobExecution.list_run_stats_by_hours(project_id)
    return render_template("server_stats.html", run_stats=run_stats)
