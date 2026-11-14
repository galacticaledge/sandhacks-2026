"""SDAPCD Community Hydrogen Sulfide Guidance (11/13/2024), quoted verbatim. Never paraphrase or invent advice.

English: https://www.sdapcd.org/content/dam/sdapcd/documents/tjrv/Community%20H2S%20Guidance_11.13.24_ENGLISH.pdf
Spanish: https://www.sdapcd.org/content/dam/sdapcd/documents/tjrv/Community%20H2S%20Guidance_11.13.24_SPANISH.pdf
"""
GUIDANCE = {
    "en": {
        "green": {"label": "Green", "range": "Less than 5 ppB",
                  "expect": "Most people will not smell an odor or experience odor-related symptoms.",
                  "actions": ["No recommendations."]},
        "yellow": {"label": "Yellow", "range": "Between 5 and 30 ppB",
                   "expect": "Some sensitive groups may smell an odor and experience odor-related symptoms such as headaches, nausea, or respiratory discomfort.",
                   "actions": ["Limit outdoor activities if you smell odor that is bothersome."]},
        "orange": {"label": "Orange", "range": "More than 30 ppB",
                   "expect": "Many people will smell an odor and/or experience odor-related symptoms.",
                   "actions": ["Limit outdoor activities if you smell odor that is bothersome.",
                               "Keep doors and windows closed to prevent odor from coming indoors.",
                               "Air out your home or building when odor is not present (by opening doors and windows, for example).",
                               "If symptoms from strong odor persists, are worrisome, or worse, seek medical care."]},
        "review": {"label": "Orange (multi-agency review)", "range": "200 ppB or higher",
                   "expect": "For levels 200 ppB or higher, SDAPCD will activate multiagency review to develop additional public recommendations if needed.",
                   "actions": ["Limit outdoor activities if you smell odor that is bothersome.",
                               "Keep doors and windows closed to prevent odor from coming indoors.",
                               "Air out your home or building when odor is not present (by opening doors and windows, for example).",
                               "If symptoms from strong odor persists, are worrisome, or worse, seek medical care."]},
    },
    "es": {
        "green": {"label": "Verde", "range": "Menos de 5 ppB",
                  "expect": "La mayoría de las personas no experimentarían olor ni síntomas.",
                  "actions": ["No hay recomendaciones."]},
        "yellow": {"label": "Amarillo", "range": "Entre 5 y 30 ppB",
                   "expect": "Los grupos sensibles pueden experimentar un olor y síntomas relacionados con el olor como dolores de cabeza, náuseas o molestias respiratorias",
                   "actions": ["Limite las actividades al aire libre si percibe un olor que le resulta molesto."]},
        "orange": {"label": "Naranja", "range": "Más de 30 ppB",
                   "expect": "Muchas personas experimentarán un olor y/o experimentarán síntomas relacionados con el olor.",
                   "actions": ["Limite las actividades al aire libre si percibe olores molestos.",
                               "Mantenga cerradas puertas y ventanas para evitar que el olor penetre en el interior.",
                               "Ventile su casa o edificio cuando no haya olores (abriendo puertas y ventanas, por ejemplo).",
                               "Si los síntomas del olor fuerte persisten, son preocupantes o empeoran, busque atención médica."]},
        "review": {"label": "Naranja (revisión multiagencia)", "range": "200 ppB o más",
                   "expect": "Para niveles de 200 ppB o más, SDAPCD activará una revisión multiagencia para desarrollar recomendaciones públicas adicionales si es necesario.",
                   "actions": ["Limite las actividades al aire libre si percibe olores molestos.",
                               "Mantenga cerradas puertas y ventanas para evitar que el olor penetre en el interior.",
                               "Ventile su casa o edificio cuando no haya olores (abriendo puertas y ventanas, por ejemplo).",
                               "Si los síntomas del olor fuerte persisten, son preocupantes o empeoran, busque atención médica."]},
    },
}
