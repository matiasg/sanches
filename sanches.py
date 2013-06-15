#!/usr/bin/env python

import json
import os
import random
import re
import string
import twitter
import urllib
from bs4 import BeautifulSoup
from collections import Counter


class Sanchez(object):
    """docstring for Sanchez"""
    ddg_cookies = {'l': 'ar-es', 'ad': 'es_AR'}
    fmts = ['Dicen {w}. {p}',
            'Sobre {w}, para tener en cuenta: {p}',
            '{p} ¡Y hablan de {w}!',
            'Se habla de {w}, pero recordemos: {p} Por favor RT',
            'Cuando todos hablan sobre {w}, yo pienso: {p}',
            'Yo el año pasado ya decía: {p}. Pensar que ahora hablan de {w}',
            ]

    def __init__(self, keys, stopwords=None):
        super(Sanchez, self).__init__()
        self.keys = keys
        self.auth = twitter.OAuth(
                keys['token'],
                keys['token_key'],
                keys['con_secret'],
                keys['con_secret_key'])

        self.twit = twitter.Twitter(auth=self.auth)
        self.count = 200

        if not stopwords:
            stopwords = os.path.join(
                    os.path.abspath(os.path.dirname(__file__)), 'stopwords.txt')
        with open(stopwords, 'r') as i:
            self.stopwords = set(l.strip() for l in i)

        self._npt = str.maketrans('', '', string.punctuation)
        self.sentences = re.compile('[A-Z][^.]+.')

    def _normal(self, w):
        return w.translate(self._npt).lower()

    def _filter_word(self, w):
        if not w: return False
        if w in self.stopwords: return False
        if len(w) < 3: return False
        if w.startswith('@'): return False
        return True

    def load_timeline(self):
        tl = self.twit.statuses.home_timeline(count=self.count)
        self.tl = []
        users_counter = Counter()
        for t in tl:
            user = t.get('user', {}).get('screen_name', '')
            if users_counter[user] < 5:
                self.tl.append(t)
                users_counter[user] += 1

    def get_words(self):
        self.load_timeline()
        normal_tweets = [' '.join(self._normal(w) for tw in self.tl for w in tw['text'].split())]
        cnt = Counter()
        for tweet in normal_tweets:
            tsp = tweet.split()
            for i in range(len(tsp)):
                if self._filter_word(tsp[i]):
                    cnt[tsp[i]] += 1
                if i + 1 >= len(tsp): continue
                if any(self._filter_word(w) for w in tsp[i : i+2]):
                    cnt['{0} {1}'.format(*tsp[i : i+2])] += 2
        return cnt

    def _take_out_tags(self, phrase):
        bs = BeautifulSoup(phrase)
        parts = bs.findAll(text=True)
        return ''.join(parts)

    def get_twitter_phrase(self, word, txt):
        phrases = self.sentences.findall(txt)
        mixed_phs = random.sample(phrases, len(phrases))
        for ph in mixed_phs:
            ph_notags = self._take_out_tags(ph)
            if self._is_ok(ph_notags):
                possible_ret = self._embelish(word, ph_notags)
                if self._is_ok_for_twitter(possible_ret):
                    return possible_ret
        return None

    def _is_ok(self, ph):
        print(ph) # sac
        if len(ph) < 8: return False  # don't want slim phrases
        if 4 < ph.find(':') < 15: return False  # don't want definitions
        if ph.startswith('REDIRECCIÓN') or ph.startswith('REDIRECT'): return False  # TODO: deal with redirections
        return True

    def _is_ok_for_twitter(self, ph):
        return len(ph) <= 140

    def wiki(self, words):
        '''Lookup words in wikipedia'''
        url = 'https://es.wikipedia.org/w/api.php?action=query&prop=info&format=json&titles=%s'
        page_url = 'https://es.wikipedia.org/w/api.php?%s'
        while words:
            w = words.pop()
            whole_url = url % urllib.parse.quote(w)
            u = urllib.request.urlopen(whole_url)
            j = json.loads(u.read().decode('utf8'))
            ids = j.get('query', {}).get('pages', None)
            if not ids or '-1' in ids: continue
            for i in ids:
                params = urllib.parse.urlencode({'action': 'query', 'pageids': i, 'prop': 'extracts', 'format': 'json'})
                u = urllib.request.urlopen(page_url % params)
                j = json.loads(u.read().decode('utf8'))
                txt = j.get('query', {}).get('pages', {}).get(i, {}).get('extract', '')
                phrase = self.get_twitter_phrase(w, txt)
                if phrase:
                    return phrase
        return None

    def ddg(self, words):
        '''Lookup words in DuckDuckGo'''
        url = 'http://api.duckduckgo.com/?%s&'
        defintn = None
        while not defintn and words:
            plc = random.randint(0, len(words) - 1)
            w = words.pop(plc)
            params = urllib.parse.urlencode({'q': w, 'format': 'json', 'ad': 'es_AR', 'l': 'ar-es'})
            u = urllib.request.urlopen(url % (params,))
            j = json.loads(u.read().decode('utf8'))
            defintn = j['Definition']
        return w, defintn

    def _embelish(self, w, p):
        f = random.sample(Sanchez.fmts, 1)[0]
        return f.format(w=w, p=p)

    def publish(self, debug):
        qtty = 15
        words = [x[0] for x in self.get_words().most_common(qtty)]
        words = random.sample(words, qtty)
        phrase = self.wiki(words)
        if phrase:
            if debug:
                print("I'm publishing:", phrase)
            self.twit.statuses.update(status=phrase)
        elif debug:
                print("Couldn't get an appropriate phrase")

import config
snch_snch_dict = config.authkeys
snch_snch = Sanchez(snch_snch_dict)

def test():
    w = snch_snch.get_words()
    print('\n'.join('%s: %d' % (wp[0], wp[1]) for wp in w.most_common(20)))

    w, d = snch_snch.wiki([x[0] for x in w.most_common(10)])
    print('{0}: {1}'.format(w, d))

if __name__ == '__main__':
    debug = False
    snch_snch.publish(debug)
