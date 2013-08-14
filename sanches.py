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

import formats


class Sanchez(object):
    """Main class, does everything"""
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

        self.prev_words = set()
        self.prev_constructs = dict([(c, 0) for c in formats.formats])
        min_tms = time.time() - non_repeat_time
        if os.path.isfile(self.previous_file):
            with open(self.previous_file, 'r') as i:
                for l in i:
                    lsp = l.strip().split('|')
                    if len(lsp) == 3:
                        w, p, t = lsp
                        c = None
                    else:
                        w, c, p, t = lsp
                    if float(t) > min_tms:
                        self.prev_words.add(w)
                        if c:
                            self.prev_constructs[c] += 1

        self._npt = str.maketrans('', '', string.punctuation)
        self.sentences = re.compile('[A-Z][^.]{4,}\.')
        self.chars_to_replace = [(re.compile('[\n:]+'), ': ')]

    def _normal(self, w):
        return w.translate(self._npt).lower()

    def _filter_word(self, w):
        if not w: return False
        if w in self.stopwords: return False
        # two-words can be made of stopwords
        if ' ' in w and all(x in self.stopwords for x in w.split()): return False
        if w in self.prev_words: return False  # no previous words
        if len(w) < 3: return False  # no short words
        if w.startswith('@'): return False  # no usernames
        if w.startswith('#'): return False  # no hashtags
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

    def get_twitter_phrase(self, word, txt, debug):
        phrases = self.sentences.findall(txt)
        mixed_phs = random.sample(phrases, len(phrases))
        for ph in mixed_phs:
            ph_notags = self._take_out_tags(ph)
            if self._is_ok(ph_notags):
                if debug: print('Considering phrase:', ph_notags)
                possible_ret, construct = self._embelish(word, ph_notags)
                if self._is_ok_for_twitter(possible_ret):
                    return possible_ret, construct
        return None, None

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

    def wiki(self, words, debug):
        '''Lookup words in wikipedia'''
        url = 'https://es.wikipedia.org/w/api.php?action=query&prop=info&format=json&titles=%s'
        page_url = 'https://es.wikipedia.org/w/api.php?%s'
        while words:
            w = words.pop()
            if debug: print('Trying word:', w)
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
                def_url = page_url % params
                if debug: print('Reading', def_url)
                u = urllib.request.urlopen(def_url)
                j = json.loads(u.read().decode('utf8'))
                txt = j.get('query', {}).get('pages', {}).get(i, {}).get('extract', '')
                phrase, construct = self.get_twitter_phrase(w, txt, debug)
                if phrase:
                    return {'word': w, 'phrase': phrase, 'construct': construct}
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
        sorted_fmts = sorted(formats.formats,
                key = lambda c: self.prev_constructs[c])
        f = random.sample(sorted_fmts[:5], 1)[0]
        callables = formats.formats[f]
        if callables:
            for part in callables:
                d[part] = callables[part](d[part])
        return f.format(**d), f

    def publish(self, debug):
        qtty = 25
        words = [x[0] for x in self.get_words(top=qtty)]
        if debug: print('Most common words:', words)
        words = random.sample(words, qtty)
        wp = self.wiki(words, debug)
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
                    o.write('{word}|{construct}|{phrase}|{ts}\n'.format(**wp))

    def _followers(self):
        return set(self.twit.followers.ids()['ids'])

    def _followed(self):
        return set(self.twit.friends.ids()['ids'])

    def followers(self):
        return self._screen_names(self._followers())

    def followed(self):
        return self._screen_names(self._followed())

    def random_sample_followers(self, screen_name, pop=1):
        followers = self.twit.followers.ids(screen_name=screen_name)['ids']
        chosen = random.sample(followers, min(pop, len(followers)))
        return self._users(chosen)

    def country(self, user):
        try:
            return user.get('status', {}).get('place', {}).get('country', None)
        except:
            return None

    def _users_few(self, ids):
        return self.twit.users.lookup(user_id=','.join([str(i) for i in ids]))

    def _users(self, ids):
        users = []
        ids_list = list(ids)
        for i in range(0, len(ids), 50):
            users.extend(self._users_few(ids_list[i : i+50]))
        return users

    def _screen_names(self, ids):
        udict = self._users(ids)
        return dict([(u['screen_name'], u['name']) for u in udict])

    def foll_foll(self, screen_name):
        users = self.twit.users.lookup(screen_name=screen_name)
        if len(users) == 0:
            return 0, 0
        return users[0]['followers_count'], users[0]['friends_count']

    def test(self):
        print(self._filter_word('en vivo'))

    def non_followed_followers(self):
        dif = self._followers() - self._followed()
        return self._screen_names(dif)

    def non_followers_followed(self):
        dif = self._followed() - self._followers()
        return self._screen_names(dif)

    def follow(self, screen_name):
        self.twit.friendships.create(screen_name=screen_name)

    def unfollow(self, screen_name):
        self.twit.friendships.destroy(screen_name=screen_name)

    def follow_non_followed(self, debug):
        nff = self.non_followed_followers()
        if debug:
            print('Will follow:', nff)
        for scrn in nff:
            self.follow(scrn)


def _get_parser():
    parser = argparse.ArgumentParser(description='Publish nonsense in Twitter')
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--test', action='store_true')
    parser.add_argument('--fnf', action='store_true', help='follow non followers')
    return parser


def main(arguments):
    """does everything (?)"""
    snch_snch_dict = config.authkeys
    snch_snch = Sanchez(snch_snch_dict)
    if arguments.test:
        snch_snch.test()
        import sys
        sys.exit()
    if arguments.fnf:
        snch_snch.follow_non_followed(arguments.debug)
    else:
        snch_snch.publish(arguments.debug)


if __name__ == '__main__':
    parser = _get_parser()
    args = parser.parse_args()
    main(args)
