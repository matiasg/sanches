#!/usr/bin/env python


import argparse
import config
import json
import os
import random
import re
import string
import time
import twitter
import urllib
from bs4 import BeautifulSoup
from collections import Counter


class Sanchez(object):
    """docstring for Sanchez"""
    lower_first = lambda x : x[0].lower() + x[1:]
    lower_first_no_period = lambda x : x[0].lower() + x[1:-1]
    fmts = ['Dicen {w}. {p}',
            'Sobre {w}, para tener en cuenta: {p}',
            '{p} ¡Y hablan de {w}!',
            'Se habla de {w}, pero recordemos: {p} Por favor RT',
            ('Cuando todos hablan sobre {w}, yo pienso: {p}', {'p': lower_first}),
            'Yo el año pasado decía "{p}" Pensar que ahora hablan de {w}.',
            ('Lo más gracioso de todo esto es: {p}', {'p': lower_first_no_period}),
            ('Cada vez que alguien dice {w}, olvida que {p}', {'p': lower_first_no_period}),
            ('¿En serio {p}?', {'p': lower_first_no_period}),
            ('Parece en joda, pero {p}', {'p': lower_first_no_period}),
            '{p} Sí, lo sé; de no creer.',
            ('{w}, y dale con {w}. ¿Por qué no piensan que {p}?', {'p': lower_first_no_period}),
            ('¿Alguien sabía que {p}?', {'p': lower_first}),
            ('Lo más loco de {w} es que {p}', {'p': lower_first}),
            ('Lamentablemente, {p}', {'p': lower_first}),
            ('Por suerte, {p}', {'p': lower_first}),
            ('Noticia urgente: {p}', {'p': lower_first}),
            ('Es raro pero {p}', {'p': lower_first}),
            ]

    def __init__(self, keys, stopwords=None, previous=None, non_repeat_time=3600*24*4):
        super(Sanchez, self).__init__()
        self.keys = keys
        self.auth = twitter.OAuth(
                keys['token'],
                keys['token_key'],
                keys['con_secret'],
                keys['con_secret_key'])

        self.twit = twitter.Twitter(auth=self.auth)
        self.count = 200

        curdir = os.path.abspath(os.path.dirname(__file__))
        if not stopwords:
            stopwords = os.path.join(curdir, 'stopwords.txt')
        with open(stopwords, 'r') as i:
            self.stopwords = set(l.strip() for l in i)

        self.previous_file = previous or os.path.join(curdir, 'previous.txt')

        self.prev_topics = set()
        min_tms = time.time() - non_repeat_time
        if os.path.isfile(self.previous_file):
            with open(self.previous_file, 'r') as i:
                for l in i:
                    w,p,t  = l.strip().split('|')
                    if float(t) > min_tms:
                        self.prev_topics.add(w)

        self._npt = str.maketrans('', '', string.punctuation)
        self.sentences = re.compile('[A-Z][^.]{4,}\.')
        self.chars_to_replace = [(re.compile('[\n:]+'), ': ')]

    def _normal(self, w):
        return w.translate(self._npt).lower()

    def _filter_word(self, w):
        if not w: return False
        if w in self.stopwords: return False
        if w in self.prev_topics: return False
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

    def get_words(self, top=15, top2=5):
        '''return top2 most common 2-word sequence and complete with (top-top2) 1-words.
        If the 2-word "A B" is in the top2, then both A and B are subtracted from the 1-words.'''
        self.load_timeline()
        normal_tweets = [' '.join(self._normal(w) for tw in self.tl for w in tw['text'].split())]
        cnt = Counter()
        cnt2 = Counter()

        # count 1-words and 2-words
        for tweet in normal_tweets:
            tsp = tweet.split()
            for i in range(len(tsp)):
                if self._filter_word(tsp[i]):
                    cnt[tsp[i]] += 1
                if i + 1 >= len(tsp): continue
                if self._filter_word(' '.join(tsp[i : i+2])):
                    cnt2['{0} {1}'.format(*tsp[i : i+2])] += 2

        # subtract 2-words from 1-words
        for ww in cnt2.most_common(top2):
            wwsplit = ww[0].split()
            cnt[wwsplit[0]] -= ww[1]
            cnt[wwsplit[1]] -= ww[1]

        # take union of most common in cnt and cnt2
        ret = set(cnt2.most_common(top2)) | set(cnt.most_common(top - top2))
        return ret

    def _take_out_tags(self, phrase):
        bs = BeautifulSoup(phrase)
        parts = bs.findAll(text=True)
        notags = ''.join(parts)
        for reg, subst in self.chars_to_replace:
            notags = reg.sub(subst, notags)
        return notags

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
        if len(ph) < 8: return False  # don't want slim phrases
        if 4 < ph.find(':') < 15: return False  # don't want definitions
        if ph.startswith('REDIRECCIÓN') or ph.startswith('REDIRECT'): return False  # TODO: deal with redirections
        if '[' in ph: return False  # avoid
        phlower = ph.lower()
        if 'wiki' in phlower: return False  # avoid Wikimedia, Wikiversity, etc.
        if 'wikciona' in phlower: return False  # avoid wikcionario
        if 'desambiguac' in phlower: return False  # avoid disambiguation phrases
        # TODO: add DISAMBIG (see independiente, carlos)
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
            try:
                u = urllib.request.urlopen(whole_url)
                j = json.loads(u.read().decode('utf8'))
            except urllib.error.URLError:
                continue  # this will most likely not work. Log something!
            ids = j.get('query', {}).get('pages', None)
            if not ids or '-1' in ids: continue
            for i in ids:
                params = urllib.parse.urlencode({'action': 'query', 'pageids': i, 'prop': 'extracts', 'format': 'json'})
                u = urllib.request.urlopen(page_url % params)
                j = json.loads(u.read().decode('utf8'))
                txt = j.get('query', {}).get('pages', {}).get(i, {}).get('extract', '')
                phrase = self.get_twitter_phrase(w, txt)
                if phrase:
                    return {'word': w, 'phrase': phrase}
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
        d = dict(w=w, p=p)
        f = random.sample(Sanchez.fmts, 1)[0]
        if type(f) != str:
            callables = f[1]
            for part in callables:
                d[part] = callables[part](d[part])
            f = f[0]
        return f.format(**d)

    def publish(self, debug):
        qtty = 15
        words = [x[0] for x in self.get_words(top=qtty)]
        words = random.sample(words, qtty)
        wp = self.wiki(words)
        if debug:
            if wp:
                print("I'm publishing:", wp['phrase'])
            else:
                print("Couldn't get an appropriate phrase")
        elif wp:
                self.twit.statuses.update(status=wp['phrase'])
                wp['ts'] = int(time.time())
                wp['phrase'] = wp['phrase'].replace('\n', ' ')  # make sure each line in previous was one tweet.
                with open(self.previous_file, 'a') as o:
                    o.write('{word}|{phrase}|{ts}\n'.format(**wp))

    def _followers(self):
        return set(self.twit.followers.ids()['ids'])

    def _followed(self):
        return set(self.twit.friends.ids()['ids'])

    def test(self):
        print(self._filter_word('en vivo'))

def _get_parser():
    parser = argparse.ArgumentParser(description='Publish nonsense in Twitter')
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--test', action='store_true')
    return parser


def main(arguments):
    """does everything (?)"""
    snch_snch_dict = config.authkeys
    snch_snch = Sanchez(snch_snch_dict)
    if arguments.test:
        snch_snch.test()
        import sys
        sys.exit()
    snch_snch.publish(arguments.debug)


if __name__ == '__main__':
    parser = _get_parser()
    args = parser.parse_args()
    main(args)
