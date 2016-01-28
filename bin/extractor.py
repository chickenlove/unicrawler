# -*- coding: utf-8 -*-
__author__ = 'yijingping'
# 加载django环境
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
os.environ['DJANGO_SETTINGS_MODULE'] = 'unicrawler.settings'
import django
django.setup()

import json
import redis
from lxml import etree
from cores.models import IndexRule, DetailRule
from cores.constants import KIND_LIST_URL, KIND_DETAIL_URL
from io import StringIO
from django.conf import settings

import logging
logger = logging.getLogger()

class Extractor():
    def extract(self, tree, rules):
        res = []
        for rule in rules:
            if rule["kind"] == "xpath":
                res = tree.xpath(rule["data"])
            elif rule["kind"] == "python":
                g, l = {}, {"in_val": res}
                try:
                    exec(rule["data"], g, l)
                    res = l["out_val"]
                except Exception as e:
                    logger.exception(e)

        return res

    def run(self):
        r = redis.StrictRedis(**settings.REDIS_OPTIONS)
        r.delete('unicrawler:urls-body')
        while True:
            try:
                data = r.brpop('unicrawler:urls-body')
            except Exception as e:
                print e
                continue
            #print data
            data = json.loads(data[1])
            body = data['body']
            htmlparser = etree.HTMLParser()
            tree = etree.parse(StringIO(body), htmlparser)
            # 如果当前接卸的页面是列表页
            if data["kind"] == KIND_LIST_URL:
                # 找下一页
                next_urls = self.extract(tree, data["next_url_rules"])
                print 'next_urls: %s' % next_urls
                for item in next_urls:
                    item_data = data.copy()
                    item_data['url'] = item
                    item_data['fresh_pages'] -= 1
                    if item_data['fresh_pages'] >= 0:
                        logger.debug('list:%s' % data['url'])
                        r.lpush('unicrawler:urls', json.dumps(item_data))

                # 找详情页
                detail_urls = self.extract(tree, data['list_rules'])
                #logger.debug('detail_urls: %s' % detail_urls)
                for item in detail_urls:
                    item_data = {
                        "url": item,
                        'kind': KIND_DETAIL_URL,
                        'rule_id': data['rule_id'],
                        'detail_rules': data['detail_rules'],
                        'seed_id': data['seed_id']
                    }
                    r.lpush('unicrawler:urls', json.dumps(item_data))
            # 如果当前接卸的页面是详情页
            elif data["kind"] == KIND_DETAIL_URL:
                logger.debug('detail:%s' % data['url'])
                rules = data['detail_rules']
                result = {
                    "url": data['url'],
                    "seed_id": data['seed_id']
                }
                for item in rules:
                    col = item["key"]
                    print col
                    col_rules = item["rules"]
                    col_value = self.extract(tree, col_rules)
                    result[col] = col_value

                r.lpush('unicrawler:data', json.dumps(result))
                logger.debug('extracted:%s' % result)


if __name__ == '__main__':
    extractor = Extractor()
    extractor.run()
