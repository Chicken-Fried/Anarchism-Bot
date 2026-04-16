from dataclasses import dataclass, field
from typing import Optional

@dataclass
class WRPLHeader:
    magic:              bytes
    version:            int
    level:              str
    level_settings:     str
    battle_type:        str
    environment:        str
    visibility:         str
    results_blk_offset: int
    difficulty:         int
    session_type:       int
    session_id:         int
    replay_part_number: int
    mset_size:          int
    settings_blk_size:  int
    loc_name:           str
    start_time:         int
    time_limit:         int
    score_limit:        int
    battle_class:       str
    battle_kill_streak: str
    is_server:          bool = False

    @property
    def session_hex(self) -> str:
        return f"{self.session_id:016x}"

@dataclass
class RawPacket:
    seq:          int
    current_time: int    # ms depuis le début de la partie
    packet_type:  int
    payload:      bytes

    TYPE_NAMES = {
        0: "EndMarker", 1: "StartMarker", 2: "AircraftSmall",
        3: "Chat",      4: "MPI",         5: "NextSegment",
        6: "ECS",       7: "Snapshot",    8: "ReplayHeaderInfo",
    }

    @property
    def type_name(self) -> str:
        return self.TYPE_NAMES.get(self.packet_type, f"Unknown({self.packet_type})")

    @property
    def time_s(self) -> float:
        return self.current_time / 1000.0

@dataclass
class PlayerFromSettings:
    """Données statiques présentes dès le header du replay."""
    slot:         int            # index dans mplace (0-based)
    name:         str
    clan_tag:     str
    user_id:      int
    team:         int            # 1 = équipe A, 2 = équipe B, 0 = unknown
    vehicle:      str            # shortname du véhicule principal
    country:      str            # nation (usa, ussr, germany, …)
    rank:         int
    exp:          int

@dataclass
class PlayerFromSlot:
    """Données dynamiques extraites des paquets Slot durant la partie."""
    slot:     int           # index 0-255
    time_ms:  int
    user_id:  int
    name:     str
    clan_tag: str
    title:    str

@dataclass
class MpiSignature:
    sig:       bytes     # 4 premiers octets
    count:     int       # nombre d'occurrences
    sizes:     list      # tailles des payloads observées (dédupliqué)
    examples:  list      # jusqu'à 5 exemples : (time_ms, payload[:48])

@dataclass
class ChatMessage:
    seq:          int
    time_ms:      int
    sender:       str
    content:      str
    channel_type: int
    is_enemy:     int

@dataclass
class KillEntry:
    seq:             int
    time_ms:         int
    damage_type:     int   # control & 0xF0 : 0x10=AP, 0x20=APHE, 0x30=HEAT, 0x40=HE/Frag
    killer_slot:     int
    killer_vehicle:  str
    victim_slot:     int   # -1 si non déterminé
    victim_vehicle:  str
    remainder_hex:   str

@dataclass
class Award:
    seq:        int
    time_ms:    int
    award_type: int
    player_slot: int
    award_name: str

@dataclass
class EntityMovement:
    seq:     int
    time_ms: int
    eid:     int
    x:       float
    y:       float
    z:       float

@dataclass
class PlayerVehicle:
    seq:               int
    slot:              int
    vehicle_id:        str | None = None
    vehicle_name:      str | None = None
    country:           str | None = None
    vehicle_type:      str | None = None
    vehicle_br:        int | None = None
    image_path:        str | None = None

@dataclass
class PlayerStats:
    """Stats de fin de partie pour un joueur, extraites du Results BLK."""
    slot:            int
    name:            str
    user_id:         int
    team:            int
    kills:           int
    deaths:          int
    assists:         int
    damage_dealt:    float
    score:           int
    activity:        float      # % d'activité (0.0–1.0)
    air_kills:       int
    ground_kills:    int
    naval_kills:     int
    vehicle:         str
    is_winner:       bool
    raw:             dict = field(default_factory=dict, repr=False)

@dataclass
class Player:
    """Vue unifiée d'un joueur, toutes sources confondues."""
    slot:         int
    name:         str
    clan_tag:     str
    user_id:      int
    team:         int
    title:        str
    # Véhicule principal (settings ou déduit des kills)
    vehicle:      str       # identifiant interne (ex: germ_panther_II)
    country:      str
    rank:         int
    # Champs avec valeurs par défaut (doivent être après les champs sans défaut)
    vehicle_name: str  = ''   # nom affiché en jeu (ex: Pz.Kpfw. Panther II) via all_units
    vehicle_type: str  = ''   # code type : MT/LT/HT/TT/AA/F/BB/BA/H
    vehicle_br:   float= 0.0  # BR réaliste sol
    vehicle_image_path: str = '' # Path de l'image de chaque vehicule
    # Tous les véhicules observés en jeu (via kills en tant que killer ou victim)
    vehicles_seen:  set = field(default_factory=set, repr=False)
    # Stats fin de partie
    lineup_vehicles: list | None = None
    kills:        int  = 0
    deaths:       int  = 0
    assists:      int  = 0
    air_kills:    int  = 0
    ground_kills: int  = 0
    naval_kills:  int  = 0
    damage_dealt: float = 0.0
    score:        int  = 0
    activity:     float = 0.0
    is_winner:    bool  = False
    # Kills commis durant la partie
    kills_recorded: list = field(default_factory=list, repr=False)
    # Awards reçus
    awards:         list = field(default_factory=list, repr=False)

@dataclass
class ReplayData:
    header:               WRPLHeader
    settings_raw:         Optional[dict]
    results_raw:          Optional[dict]
    players:              dict            # slot → Player
    chats:                list = field(default_factory=list)
    kills:                list = field(default_factory=list)
    movements:            list = field(default_factory=list)
    awards:               list = field(default_factory=list)
    packet_count:         int  = 0
    unknown_slot_msgs:    list = field(default_factory=list)  # messages slot non-parsés

@dataclass
class VehicleInfo:
    """Métadonnées d'un véhicule WT issues du all_units.json (all_units.py)."""
    id:               str
    display_name:     str    # Nom affiché en jeu (ex: "Pz.Kpfw. Panther II")
    country:          str    # Nation WT (ex: "germany", "ussr", "usa"…)
    vehicle_type:     str    # Code court : MT/LT/HT/TT/AA/F/BB/BA/H
    vehicle_full_type: str   # Type long (ex: "medium_tank", "fighter"…)
    br:               float = 0.0  # BR réaliste sol
    image_path:       str = ''   # Path de l'image de chaque véhicule

    @classmethod
    def from_dict(cls, d: dict) -> VehicleInfo:
        """Construit depuis un dict all_units.json (clés variables selon la source)."""
        return cls(
            id               = d.get('unit_full_name') or "",
            display_name     = d.get('full_name')      or d.get('display_name', ''),
            country          = d.get('country', ''),
            vehicle_type     = d.get('vehicle_type', ''),
            vehicle_full_type= d.get('vehicle_full_type') or d.get('vehicle_full_type', ''),
            br               = float(d.get('realistic_ground_br') or d.get('br') or 0),
            image_path       = d.get('image_path')
        )
