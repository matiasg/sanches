'''Formats for embellishing phrases.
When a word w produces a phrase p, keys in formats
get {w} and {p} replaced by w and p respectively.
Also, values tell how to convert each argument.
'''

# put first letter as lowercase
lower_first = lambda x : x[0].lower() + x[1:]

# put first letter as lowercase and take last char
lower_first_no_period = lambda x : x[0].lower() + x[1:-1]

# put first letter as uppercase
upper_first = lambda x : x[0].upper() + x[1:]

# take last char out
no_period = lambda x : x[:-1]

formats = {
    'Dicen {w}. {p}': None,
    'Sobre {w}, para tener en cuenta: {p}': None,
    '{p} ¡Y hablan de {w}!': None,
    'Se habla de {w}, pero recordemos: {p} Por favor RT': None,
    'Cuando todos hablan sobre {w}, yo pienso: {p}': {'p': lower_first},
    'Yo el año pasado decía "{p}" Pensar que ahora hablan de {w}.': None,
    'Lo más gracioso de todo esto es: {p}': {'p': lower_first_no_period},
    'Cada vez que alguien dice {w}, olvida que {p}': {'p': lower_first_no_period},
    '¿En serio {p}?': {'p': lower_first_no_period},
    'Parece en joda, pero {p}': {'p': lower_first_no_period},
    '{p} Sí, lo sé; de no creer.': None,
    '{w}, y dale con {w}. ¿Por qué no piensan que {p}?': {'p': lower_first_no_period, 'w': upper_first},
    '¿Alguien sabía que {p}?': {'p': lower_first_no_period},
    'Lo más loco de {w} es que {p}': {'p': lower_first},
    'Lamentablemente, {p}': {'p': lower_first},
    'Por suerte, {p}': {'p': lower_first},
    'Noticia urgente: {p}': {'p': lower_first},
    'Es raro pero {p}': {'p': lower_first},
    '{p}': None,
    'Hablando de {w}, {p}': {'p': lower_first},
    'Ma que {w} ni {w}? {p}!': {'p': no_period},
    'No me hagan hablar de {w} porque digo que {p}': {'p': lower_first},
    '{p} Daría ganas de reír si no diera ganas de llorar.': None,
    '{p} Daría ganas de llorar si no diera ganas de reír.': None,
    '{p}! Mátenme.': {'p': no_period},
    }
