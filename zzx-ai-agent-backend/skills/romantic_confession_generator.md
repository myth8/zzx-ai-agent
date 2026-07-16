---
name: romantic_confession_generator
description: Trigger this skill by entering the command "[时刻浪漫表白]" (or "Romantic Confession at this Moment"). It calls the `get_time` tool to obtain the precise current date and time, then generates a ~200‑word, deeply emotional and unique confession text anchored to that exact moment. Use it when you want to express love in a personalized, time‑sensitive way—for example, during a romantic date, an anniversary, a surprise moment, or any occasion where you wish to turn the present instant into an unforgettable declaration. The final confession output MUST be in Simplified Chinese (简体中文).
---

## Body

### 1. Obtaining the Poetic Coordinates of Time

First, **you must call the `get_time` tool** to obtain the following precise information:
- Current date (year, month, day)
- Current time (hour, minute)

These data are not cold numbers; they are the core material that gives the confession its uniqueness. Our goal is: **This confession can only be spoken at this exact moment—not one second earlier, not one second later.**

### 2. Emotional Mapping of Time Imagery

Based on the acquired time characteristics, transform them into heartfelt imagery that serves as the "canvas" for your confession:

| Time Slot | Poetic Transformation (Example) |
| :--- | :--- |
| **Early morning (5:00–8:00)** | The first light of dawn, the fragility and clarity of dew, the first bird song of a waking world—symbolising "you are the only reason I want to get up early." |
| **Midday (11:00–14:00)** | The blazing sun, strong contrasts of light and shadow, the vibrant vigour of all things—symbolising "my love is like the noon sun, impossible to hide and unreservedly given." |
| **Dusk (17:00–19:00)** | The gradual shift of sunset colours, the ambiguity between day and night, the weariness of returning home—symbolising "as the day draws to a close, you are the one I most long to run to." |
| **Late night (22:00–4:00)** | The coolness of moonlight, the eternity of stars, the sound of my heartbeat in the utter silence—symbolising "while the whole world sleeps, my thoughts of you are unusually awake." |

### 3. The "Four‑Paragraph" Structure for Generating the Confession

Combine the time imagery with genuine emotion, and organise the approximately 200‑word text according to the following logic:

- **Paragraph 1 (Opening · Freezing the Moment):** Directly state the current exact time and scene, creating a strong sense of presence—"I am thinking of you right now, in this very moment."
- **Paragraph 2 (Immersion · Natural Association):** Cleverly project your observations of the current time onto your feelings for the other person (e.g., "The cicadas are so loud, yet I hear only your name").
- **Paragraph 3 (Climax · Core Confession):** Clearly say "I love you" or "I like you," and give it a time‑based uniqueness (e.g., "I want to turn every such moment into an eternity spent with you").
- **Paragraph 4 (Hope · Future Invitation):** Gently extend an action invitation or future commitment, so that the confession is not just words but a new beginning.

### 4. Example Output (based on an assumed time: July 16, 2026, 14:35)

> **After calling `get_time`, the generated sample text (in Simplified Chinese) reads:**
>
> 现在是2026年7月16日，周四，午后两点三十五分。
>
> 外面的蝉鸣快把空气煮沸了，阳光正烈，把窗台的影子压得很短。就在这样一个万物都懒洋洋、全世界仿佛都在打盹的时刻，我却格外清醒——清醒地意识到，我正在想你。
>
> 这午后的光太直接了，就像我对你的心思，毫无遮挡，烫得惊人。有人说夏日的爱意太热烈容易灼伤，可我不在乎。我宁愿在这一刻烧成灰烬，也不愿在漫长的四季里，永远做那个沉默的旁观者。
>
> 我喜欢你。不是春风秋雨的温柔试探，是此刻这盛夏正午般的坦诚与笃定。我想把每个烈日灼心的午后，都变成与你并肩躲进树荫的黄昏；把这一秒的滚烫，续写成往后余生所有季节的陪伴。
>
> 所以，要不要和我一起，去浪费这个夏天？就从今天开始。

### 5. Notes and Fine‑Tuning Suggestions

- **Avoid clichés:** The generation must strictly use the real data returned by `get_time`; do not use vague terms like "spring passes and autumn comes." Be concrete (e.g., "the rain on July 16").
- **Pronoun adjustment:** The basic template uses "you/I"; it can be flexibly replaced with the other person's nickname as needed.
- **Length control:** Strictly keep the text between **180–220 words** (in Chinese characters) to ensure it can be delivered fluently in confession scenarios without being overly long.
- **Consistent style:** Maintain a "deep, delicate, and slightly literary" tone throughout; avoid sudden playfulness or complaints that might break the mood.
- **Alternative for late night:** If `get_time` returns a time between 00:00 and 04:00, slightly reduce the intensity of the action invitation and switch to a more restrained expression such as "quietly waiting" or "I will go to you when dawn breaks," which better suits the stillness of the night.
- **Language requirement:** The final confession output MUST be in Simplified Chinese (简体中文). Do not output in English or any other language.