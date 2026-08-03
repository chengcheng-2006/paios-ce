"""Pydantic config models: PublicConfig, PrivateConfig, RuntimeConfig.

MUST NEVER contain secret values. Provider credentials appear only as
SecretRef declarations (backend + reference label), never as raw values.
Placeholders only (example.invalid / 127.0.0.1 / not-a-valid-provider-token).

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Cheng Cheng
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

PUBLIC_CONFIG_SCHEMA = "https://paios.ce/schemas/public-config/v0.1.json"
PRIVATE_CONFIG_SCHEMA = "https://paios.ce/schemas/private-config/v0.1.json"
RUNTIME_CONFIG_SCHEMA = "https://paios.ce/schemas/runtime-config/v0.1.json"

Profile = Literal["minimal", "standard", "full", "custom"]
RuntimeProfile = Literal["lite", "standard", "distributed_optional"]
SupportLevel = Literal["v0_1_supported", "experimental", "planned", "community"]
SpeechSupportLevel = Literal["v0_1_supported", "experimental", "planned", "unavailable"]


class SecretRefDecl(BaseModel):
    """A SecretRef *declaration* (never a value)."""

    model_config = ConfigDict(extra="forbid")

    backend: Literal["env", "oskeyring", "dpapi", "file", "external_manager", "prompt_once"]
    ref: Dict[str, str] = Field(default_factory=dict)


class DefaultsConfig(BaseModel):
    """Frozen security defaults (public config)."""

    model_config = ConfigDict(extra="forbid")

    listen: str = "127.0.0.1"
    public_bind: bool = False
    public_bind_risk_acknowledged: bool = False
    dm_only: bool = True
    group_execution: bool = False
    group_execution_risk_acknowledged: bool = False
    owner_allowlist_required: bool = True
    high_risk_confirmation: bool = True
    raw_audio_storage: bool = False
    temp_audio_delete: bool = True
    cloud_asr: Literal["opt_in_only", "disabled"] = "opt_in_only"
    remote_execution: bool = False


class ProviderEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    support_level: SupportLevel = "planned"
    credential_ref: Optional[SecretRefDecl] = None


class ChannelEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    support_level: SupportLevel = "planned"
    credential_ref: Optional[SecretRefDecl] = None


class SpeechEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    support_level: SpeechSupportLevel = "planned"


class CapabilitiesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    providers: List[ProviderEntry] = Field(default_factory=list)
    channels: List[ChannelEntry] = Field(default_factory=list)
    speech: List[SpeechEntry] = Field(default_factory=list)


class AuditConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    redact_secret_values: bool = True
    redact_paths: bool = True
    redact_endpoints: bool = True
    transcript_retention_days: int = Field(default=0, ge=0)


class InstallerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_profile: Optional[Profile] = None
    optional_components_eligible: List[str] = Field(default_factory=list)


class PublicConfig(BaseModel):
    """Public project config — reproducible, no secrets, references only."""

    model_config = ConfigDict(extra="forbid")

    schema: Literal["https://paios.ce/schemas/public-config/v0.1.json"] = PUBLIC_CONFIG_SCHEMA
    profile: Profile = "minimal"
    runtime_profile: RuntimeProfile = "lite"
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)
    capabilities: CapabilitiesConfig = Field(default_factory=CapabilitiesConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)
    installer: InstallerConfig = Field(default_factory=InstallerConfig)


class PrivateProviderEntry(BaseModel):
    """Provider entry in private config; credential via SecretRef only."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    endpoint: str = Field(default="https://example.invalid/v1", max_length=1024)
    credential_ref: Optional[SecretRefDecl] = None


class LocalWebChannel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    listen: str = "127.0.0.1"
    port: int = Field(default=8080, ge=1, le=65535)
    public_bind: bool = False
    public_bind_risk_acknowledged: bool = False


class CliChannel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True


class PrivateChannels(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local_web: LocalWebChannel = Field(default_factory=LocalWebChannel)
    cli: CliChannel = Field(default_factory=CliChannel)


class PrivateSpeech(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    asr_backend: Literal["local_faster_whisper", "cloud_opt_in", "disabled"] = "disabled"
    raw_audio_storage: bool = False
    temp_audio_delete: bool = True
    transcript_retention_days: int = Field(default=0, ge=0)
    cloud_asr_opt_in: bool = False


class PrivateState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sqlite_path: Optional[str] = None
    model_cache_path: Optional[str] = None


class GroupExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    risk_acknowledged: bool = False


class PrivateConfig(BaseModel):
    """Private local config — created by end user, never committed."""

    model_config = ConfigDict(extra="forbid")

    schema: Literal["https://paios.ce/schemas/private-config/v0.1.json"] = PRIVATE_CONFIG_SCHEMA
    # Phase 2 schema: owner_allowlist is required and minItems 1.
    owner_allowlist: List[str] = Field(default_factory=list, min_length=1)
    providers: Dict[str, PrivateProviderEntry] = Field(default_factory=dict)
    channels: PrivateChannels = Field(default_factory=PrivateChannels)
    speech: PrivateSpeech = Field(default_factory=PrivateSpeech)
    state: PrivateState = Field(default_factory=PrivateState)
    group_execution: GroupExecutionConfig = Field(default_factory=GroupExecutionConfig)


class RuntimeConfig(BaseModel):
    """Merged effective runtime configuration after precedence resolution."""

    model_config = ConfigDict(extra="forbid")

    schema: Literal["https://paios.ce/schemas/runtime-config/v0.1.json"] = RUNTIME_CONFIG_SCHEMA
    profile: Profile = "minimal"
    runtime_profile: RuntimeProfile = "lite"
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)
    owner_allowlist: List[str] = Field(default_factory=list)
    primary_provider: str = "mock"
    fallback_provider: Optional[str] = None
    provider_endpoint: str = "https://example.invalid/v1"
    provider_credential_ref: Optional[SecretRefDecl] = None
    channels: PrivateChannels = Field(default_factory=PrivateChannels)
    speech: PrivateSpeech = Field(default_factory=PrivateSpeech)
    state: PrivateState = Field(default_factory=PrivateState)
    audit: AuditConfig = Field(default_factory=AuditConfig)
    group_execution: GroupExecutionConfig = Field(default_factory=GroupExecutionConfig)
