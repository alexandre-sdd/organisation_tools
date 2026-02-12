from pydantic import BaseModel, ConfigDict, Field


class Experience(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = ""
    company: str = ""


class Education(BaseModel):
    model_config = ConfigDict(extra="ignore")

    school: str = ""


class MyProfile(BaseModel):
    # Keep extra keys to remain backward-compatible with extension payloads.
    model_config = ConfigDict(extra="allow")

    headline: str = ""
    location: str = ""
    schools: list[str] = Field(default_factory=list)
    experiences: list[str] = Field(default_factory=list)
    proof_points: list[str] = Field(default_factory=list)
    focus_areas: list[str] = Field(default_factory=list)
    internship_goal: str = ""
    do_not_say: list[str] = Field(default_factory=list)
    tone_preference: str = "warm"


class TargetProfile(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = ""
    headline: str = ""
    location: str = ""
    about: str = ""
    top_experiences: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    my_profile: MyProfile = Field(default_factory=MyProfile)
    target_profile: TargetProfile = Field(default_factory=TargetProfile)
    hooks: list[str] = Field(default_factory=list)


class Variant(BaseModel):
    label: str
    text: str
    char_count: int


class GenerateResponse(BaseModel):
    variants: list[Variant] = Field(default_factory=list)
