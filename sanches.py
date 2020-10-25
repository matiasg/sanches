#!/usr/bin/env python

import argparse
import time
import os
import random
import re
import string
import logging
from collections import Counter
from dataclasses import dataclass
from typing import List, Dict
import warnings

import yaml
import twitter
import wikipedia
import spacy


wikipedia.set_lang("es")
nlp = spacy.load('es_core_news_sm')
logger = logging.getLogger(__name__)


@dataclass
class PublishingData:
    '''Data class for publishing info'''

    word: str
    page: str
    sentence: str
    timestamp: int = 0

    def make_twitt(self) -> str:
        '''Produce the twitt to be published'''
        return f'{self.word}: {self.sentence}'

    def is_ok(self) -> bool:
        '''Tell whether twitt would be ok to publish'''
        twit = self.make_twitt()
        return len(twit) < 280

    def csvline(self) -> str:
        '''csv serialization'''
        return f'{self.word}|{self.page}|{self.sentence}|{self.timestamp}'

    @classmethod
    def from_csvline(cls, line):
        '''returns a PublishingData from a |-separated line. Converse of csvline'''
        return cls(*line.split('|'))


class Wiki:
    '''Class for dealing with wikipedia'''

    @classmethod
    def get_page(cls, word):
        try:
            logger.debug("Looking for page for: %s", word)
            text = wikipedia.page(word)
            return word, nlp(text.content)
        except wikipedia.DisambiguationError as exc:
            options = set(exc.options) - {word}  # avoid choosing again the same word
            next_word = random.choice(list(options))
            logger.debug("Disambiguation, Choosing %s between %s", next_word, options)
            return cls.get_page(next_word)

    @classmethod
    def get_sentences(cls, doc):
        return list(doc.sents)

    @classmethod
    def good_sentence(cls, sentence: str) -> bool:
        '''returns whether a sentence is good for a tweet'''
        good = True
        if re.search(r'\[\d+\]', sentence):
            good = False  # don't want footnotes
        if len(sentence) < 8:
            good = False  # don't want slim sentences
        if 4 < sentence.find(':') < 15:
            good = False  # don't want definitions
        if sentence.startswith('REDIRECCIÓN') or sentence.startswith('REDIRECT'):
            good = False  # TODO: deal with redirections
        sent_lower = sentence.lower()
        if 'wiki' in sent_lower:
            good = False  # avoid Wikimedia, Wikiversity, etc.
        if 'wikciona' in sent_lower:
            good = False  # avoid wikcionario
        if 'desambiguac' in sent_lower:
            good = False  # avoid disambiguation sentences

        return good

    @classmethod
    def random_sentence(cls, word):
        try:
            final_word, doc = cls.get_page(word)
        except wikipedia.PageError:
            return None

        sents = cls.get_sentences(doc)
        pub_datas = [PublishingData(word, final_word, sent.text) for sent in sents]
        good = [pd for pd in pub_datas if cls.good_sentence(pd.sentence) and pd.is_ok()]
        weights = [1/i for i, _ in enumerate(good, 1)]
        logger.debug('Good sentences: %s', good)
        return random.choices(good, weights=weights, k=1)[0]

    @classmethod
    def random_sentence_for_words(cls, words: List[str]) -> PublishingData:
        for word in words:
            ret = cls.random_sentence(word)
            if ret is not None and ret.is_ok():
                return ret
        return None


class TwitterManager:
    '''Class for dealing with Twitter API'''

    def __init__(self, keys):
        auth = twitter.OAuth(
                keys['token'],
                keys['token_key'],
                keys['api_key'],
                keys['api_secret_key'])

        self.twit = twitter.Twitter(auth=auth)
        self.count = 200

    def get_timeline(self) -> List[Dict]:
        ret = []
        timeline = self.twit.statuses.home_timeline(count=self.count)
        users_counter = Counter()
        for twitt in timeline:
            user = twitt.get('user', {}).get('screen_name', '')
            if users_counter[user] < 5:  # don't add too many tweets from the same user
                ret.append(twitt)
                users_counter[user] += 1
        return ret

    @classmethod
    def _merge(cls, x):
        if isinstance(x, str):
            return [x]
        if isinstance(x, list):
            return sum((cls._merge(y) for y in x), [])
        if isinstance(x, dict):
            return sum((cls._merge(y) for y in x.values()), [])
        return []


    def _unwanted(self, tweet: Dict) -> List[str]:
        return self._merge(tweet['entities'])

    def _words_from_tweet(self, tweet):
        # TODO: use spacy
        # TODO 2: what happens if tweet['truncated'] is True?
        return tweet['text'].split()

    def get_clean_timeline_as_texts(self) -> List[str]:
        timeline = self.get_timeline()
        ret = []
        for tweet in timeline:
            unwanted = self._unwanted(tweet)
            good_words = [word for word in self._words_from_tweet(tweet)
                          if word not in unwanted]
            ret.append(good_words)
        return ret

    def publish(self, content):
        logger.info('publishing: %s', content)
        self.twit.statuses.update(status=content)

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

    def follow_non_followed(self, dry_run):
        nff = self.non_followed_followers()
        if dry_run:
            logger.info('Will follow: %s', nff)
        for scrn in nff:
            self.follow(scrn)


class Sanchez:
    """Main class, does everything"""

    def __init__(self, keys, stopwords_file=None, previous=None, non_repeat_time=3600*24*4):
        self.twitter = TwitterManager(keys)
        curdir = os.path.abspath(os.path.dirname(__file__))
        if not stopwords_file:
            stopwords_file = os.path.join(curdir, 'stopwords.txt')
        with open(stopwords_file, 'r') as sw_fd:
            self.stopwords = set(word.strip() for word in sw_fd)

        self.previous_file = previous or os.path.join(curdir, 'previous.txt')

        self.prev_words = set()
        min_tms = time.time() - non_repeat_time
        if os.path.isfile(self.previous_file):
            with open(self.previous_file, 'r') as pf_fd:
                for line in pf_fd:
                    p_data = PublishingData.from_csvline(line)
                    if float(p_data.timestamp) > min_tms:
                        self.prev_words.add(p_data.word)

        self._npt = str.maketrans('', '', string.punctuation)
        self.sentences = re.compile(r'[A-Z][^.]{4,}\.')
        self.chars_to_replace = [(re.compile('[\n:]+'), ': ')]

    def _normal(self, word):
        return word.translate(self._npt).lower()

    def good_word(self, word: str) -> bool:
        good = True
        if not word:
            good = False
        if all(x in self.stopwords for x in word.split()):
            good = False
        if word in self.prev_words:
            good = False  # no previous words
        if len(word) < 3:
            good = False  # no short words
        # if word.startswith('@'):
        #     good = False  # no usernames
        # if word.startswith('#'):
        #     good = False  # no hashtags
        if word.startswith('https'):
            good = False
        return good

    def get_words(self, top=15, top2=5):
        '''return :top2: most common 2-word sequence and complete with (:top: - :top2:) 1-words.
        If the 2-word "A B" is in the top2, then both A and B are subtracted from the 1-words.'''
        timeline = self.twitter.get_clean_timeline_as_texts()
        normal_tweets = [' '.join(self._normal(w)
                                  for tw in timeline
                                  for w in tw)]
        cnt = Counter()
        cnt2 = Counter()

        # count 1-words and 2-words
        for tweet in normal_tweets:
            tsp = tweet.split()
            for i, word in enumerate(tsp):
                if self.good_word(word):
                    cnt[word] += 1
                if i + 1 >= len(tsp):
                    continue
                if self.good_word(' '.join(tsp[i:i+2])):
                    cnt2['{0} {1}'.format(*tsp[i:i+2])] += 2

        # subtract 2-words from 1-words
        for two_word in cnt2.most_common(top2):
            word1, word2 = two_word[0].split()
            cnt[word1] -= two_word[1]
            cnt[word2] -= two_word[1]

        # take union of most common in cnt and cnt2
        ret = set(cnt2.most_common(top2)) | set(cnt.most_common(top - top2))
        return ret

    # def _take_out_tags(self, phrase):
    #     bs = BeautifulSoup(phrase)
    #     parts = bs.findAll(text=True)
    #     notags = ''.join(parts)
    #     for reg, subst in self.chars_to_replace:
    #         notags = reg.sub(subst, notags)
    #     return notags

    # def get_twitter_phrase(self, word, txt, debug):
    #     phrases = self.sentences.findall(txt)
    #     mixed_phs = random.sample(phrases, len(phrases))
    #     for ph in mixed_phs:
    #         ph_notags = self._take_out_tags(ph)
    #         if self._is_ok(ph_notags):
    #             if debug: print('Considering phrase:', ph_notags)
    #             possible_ret, construct = self._embelish(word, ph_notags)
    #             if self._is_ok_for_twitter(possible_ret):
    #                 return possible_ret, construct
    #     return None, None

    # def ddg(self, words):
    #     '''Lookup words in DuckDuckGo'''
    #     url = 'http://api.duckduckgo.com/?%s&'
    #     defintn = None
    #     while not defintn and words:
    #         plc = random.randint(0, len(words) - 1)
    #         w = words.pop(plc)
    #         params = urllib.parse.urlencode({'q': w, 'format': 'json', 'ad': 'es_AR', 'l': 'ar-es'})
    #         u = urllib.request.urlopen(url % (params,))
    #         j = json.loads(u.read().decode('utf8'))
    #         defintn = j['Definition']
    #     return w, defintn

    # def _embelish(self, w, p):
    #     d = dict(w=w, p=p)
    #     sorted_fmts = sorted(formats.formats,
    #             key = lambda c: self.prev_constructs[c])
    #     f = random.sample(sorted_fmts[:5], 1)[0]
    #     callables = formats.formats[f]
    #     if callables:
    #         for part in callables:
    #             d[part] = callables[part](d[part])
    #     return f.format(**d), f

    def publish(self, dry_run):
        qtty = 25
        words = [x[0] for x in self.get_words(top=qtty)]
        logger.info('Most common words: %s', words)
        words = random.sample(words, qtty)
        pub_data = Wiki.random_sentence_for_words(words)

        if pub_data is None:
            logger.warning("Couldn't get an appropriate phrase")
            exit(1)

        logger.info("I'm publishing: %s", pub_data.make_twitt())

        if not dry_run:
            self.twitter.publish(pub_data.make_twitt())
            self.save_published_data(pub_data)

    def save_published_data(self, pub_data):
        pub_data.timestamp = int(time.time())
        pub_data.sentence = pub_data.sentence.replace('\n', ' ')  # make sure each line in previous was one tweet.
        with open(self.previous_file, 'a') as previous:
            previous.write(f'{pub_data.csvline()}\n')


def _get_parser():
    parser = argparse.ArgumentParser(description='Publish nonsense in Twitter')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--fnf', action='store_true', help='follow non followers')
    return parser


def load_config():
    with open('config.yaml') as cfg_fd:
        conf = yaml.load(cfg_fd, Loader=yaml.Loader)
    return conf


def main(arguments):
    """does everything (?)"""
    snch_snch_dict = load_config()
    snch_snch = Sanchez(snch_snch_dict)
    if arguments.fnf:
        snch_snch.twitter.follow_non_followed(arguments.dry_run)
    else:
        snch_snch.publish(arguments.dry_run)


if __name__ == '__main__':
    logger.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)

    formatter = logging.Formatter('[%(levelname)s] %(message)s')
    ch.setFormatter(formatter)

    logger.addHandler(ch)

    parser = _get_parser()
    args = parser.parse_args()
    main(args)
