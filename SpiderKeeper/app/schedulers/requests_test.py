import requests

from SpiderKeeper.app.util.http import request_get
web_url = 'https://www.baidu.com'
rst = request_get(url=web_url, retry_times=2)
if rst is None:
    print("断开连接")
else:
    print(rst)

# res = requests.get(web_url)
# print(res.status_code)