"""Schemas that generated content must satisfy."""

from pydantic import BaseModel, ConfigDict, Field

LINKEDIN_MAX_CHARS = 3000


class LinkedInPost(BaseModel):
    model_config = ConfigDict(extra="ignore")
    body: str = Field(min_length=1, max_length=LINKEDIN_MAX_CHARS)
    hashtags: list[str] = []


class LinkedInPosts(BaseModel):
    model_config = ConfigDict(extra="ignore")
    posts: list[LinkedInPost]


TWEET_MAX_CHARS = 280


class Tweet(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str = Field(min_length=1, max_length=TWEET_MAX_CHARS)


class Tweets(BaseModel):
    model_config = ConfigDict(extra="ignore")
    tweets: list[Tweet]


YOUTUBE_TITLE_MAX_CHARS = 100  # YouTube's own title limit


class YouTubeScript(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str = Field(min_length=1, max_length=YOUTUBE_TITLE_MAX_CHARS)
    hook: str = Field(min_length=1)
    body: str = Field(min_length=1)
    call_to_action: str = Field(min_length=1)


class YouTubeScripts(BaseModel):
    model_config = ConfigDict(extra="ignore")
    scripts: list[YouTubeScript]


SUBSTACK_NOTE_MAX_CHARS = 800


class SubstackNote(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str = Field(min_length=1, max_length=SUBSTACK_NOTE_MAX_CHARS)


class SubstackNotes(BaseModel):
    model_config = ConfigDict(extra="ignore")
    notes: list[SubstackNote]


NEWSLETTER_HEADING_MAX_CHARS = 100


class NewsletterSection(BaseModel):
    model_config = ConfigDict(extra="ignore")
    heading: str = Field(min_length=1, max_length=NEWSLETTER_HEADING_MAX_CHARS)
    body: str = Field(min_length=1)


class NewsletterSections(BaseModel):
    model_config = ConfigDict(extra="ignore")
    sections: list[NewsletterSection]


INSTAGRAM_CAPTION_MAX_CHARS = 2200


class InstagramCaption(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str = Field(min_length=1, max_length=INSTAGRAM_CAPTION_MAX_CHARS)


class InstagramCaptions(BaseModel):
    model_config = ConfigDict(extra="ignore")
    captions: list[InstagramCaption]
