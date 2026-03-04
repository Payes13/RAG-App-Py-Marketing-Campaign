"""
Campaign generation prompt template.

Uses ChatPromptTemplate with few-shot examples exactly as specified in CLAUDE.md.
"""
from langchain_core.prompts import ChatPromptTemplate

SYSTEM_ROLE = """You are an expert marketing specialist for an airline. Your job is to create
compelling, data-driven marketing campaigns based on real customer data.
Always write in a warm, engaging tone. Never mention specific prices.
Always include an unsubscribe option reminder."""

FEW_SHOT_EXAMPLES = """
--- EXAMPLE 1 (family-focused route campaign, Spanish) ---
Input: Route: Montreal-San Salvador, Audience: familias jóvenes con hijos, Language: es, Tone: warm and exciting
Output:
{
  "subject_line": "¡Lleva a tu familia al paraíso! ✈️",
  "preview_text": "Descubre San Salvador con tus seres queridos esta temporada",
  "body": "Querida familia viajera,\\n\\nSabemos cuánto valoras los momentos especiales con tus hijos. Por eso, queremos invitarte a descubrir la magia de San Salvador: playas impresionantes, cultura vibrante y experiencias inolvidables para toda la familia.\\n\\nNuestros vuelos desde Montreal te ofrecen comodidad y calidez desde el primer momento. Viaja en familia y crea memorias que durarán toda la vida.\\n\\n¡Es el momento perfecto para vivir una aventura juntos!\\n\\nPara cancelar suscripción, haz clic aquí.",
  "cta": "¡Reserva tu aventura familiar!"
}

--- EXAMPLE 2 (business traveler campaign, English) ---
Input: Route: Toronto-New York, Audience: frequent business travelers, Language: en, Tone: professional and efficient
Output:
{
  "subject_line": "Your next business trip, upgraded",
  "preview_text": "Premium service for Toronto-New York professionals",
  "body": "Dear valued traveler,\\n\\nAs a frequent business traveler between Toronto and New York, your time is your most valuable asset. We understand that. That's why we've designed a travel experience built around your schedule, comfort, and productivity.\\n\\nEnjoy priority boarding, premium seating, and seamless connections that let you arrive ready to perform at your best. Because successful professionals deserve a journey as polished as their work.\\n\\nFly smarter. Arrive stronger.\\n\\nTo unsubscribe from marketing emails, click here.",
  "cta": "Book your business flight"
}
"""

HUMAN_TEMPLATE = """--- AUDIENCE DATA (from customer database and CSV analysis) ---
{audience_data}

--- PREVIOUS CAMPAIGN CONTEXT (from PDF documents) ---
{marketing_context}

--- SPECIFIC INSTRUCTIONS ---
Generate a {campaign_type} campaign for the route {route}.
Target audience: {audience_description}
Language: {language}

The campaign must include:
- Subject line (max 50 characters)
- Preview text (max 90 characters)
- Email body (max 200 words)
- One clear CTA button text
- Tone: {tone}

--- RESTRICTIONS ---
- Do not mention specific prices
- Do not use technical jargon
- Always include unsubscribe reminder
- Output must be valid JSON with exactly these keys: subject_line, preview_text, body, cta
"""


def get_campaign_prompt() -> ChatPromptTemplate:
    """
    Build and return the ChatPromptTemplate for campaign generation.
    Sections in order: System role → Few-shot examples → Audience context →
    Marketing context → Specific instructions → Restrictions.
    """
    return ChatPromptTemplate.from_messages([
        ("system", SYSTEM_ROLE + "\n\n" + FEW_SHOT_EXAMPLES),
        ("human", HUMAN_TEMPLATE),
    ])
