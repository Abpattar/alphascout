"""
Ticker Mapper - Resolves company names to NSE tickers
Uses universe + fuzzy matching + known aliases
"""
import re
from dataclasses import dataclass
from difflib import get_close_matches
from typing import Dict, List, Optional, Set

from src.universe.builder import get_universe


# Known aliases for common companies
TICKER_ALIASES = {
    # Defence
    "data patterns": "DATAPATTNS.NS",
    "mtar technologies": "MTARTECH.NS",
    "mtar": "MTARTECH.NS",
    "paras defence": "PARASDEF.NS",
    "paras": "PARASDEF.NS",
    "astra microwave": "ASTRAMICRO.NS",
    "astra": "ASTRAMICRO.NS",
    "zen technologies": "ZENTEC.NS",
    "zen": "ZENTEC.NS",
    "ideafoge": "IDEAFORGE.NS",
    "apollo micro": "APOLLOMICRO.NS",
    "apollo micro systems": "APOLLOMICRO.NS",
    "solar industries": "SOLIND.NS",
    "bharat dynamics": "BDL.NS",
    "bdl": "BDL.NS",
    "mazagon dock": "MAZDOCK.NS",
    "mazagon": "MAZDOCK.NS",
    "cochin shipyard": "COCHINSHIP.NS",
    "grse": "GRSE.NS",
    "garden reach": "GRSE.NS",
    "bharat forge": "BHARATFORG.NS",
    "l&t defence": "LT.NS",
    "larsen toubro": "LT.NS",

    # Railways
    "rvnl": "RVNL.NS",
    "irfc": "IRFC.NS",
    "irctc": "IRCTC.NS",
    "titagarh": "TITAGARH.NS",
    "beml": "BEML.NS",
    "texmaco": "TEXMACO.NS",
    "rcon": "RCON.NS",
    "jwl": "JWL.NS",

    # EV
    "olectra": "OLECTRA.NS",
    "jbm auto": "JBMA.NS",
    "exide": "EXIDEIND.NS",
    "amara raja": "AMARAJABAT.NS",
    "himadri": "HIMADRI.NS",
    "graphite india": "GRAPHITE.NS",

    # Renewable
    "borosil": "BOROSIL.NS",
    "premier ener": "PREMIERENE.NS",
    "waaree": "WAAREE.NS",
    "inox wind": "INOXWIND.NS",
    "suzlon": "SUZLON.NS",
    "orient green": "ORIENTGREN.NS",
    "kpil": "KPIL.NS",
    "sterling wilson": "STERLING.NS",
    "gensol": "GENSOL.NS",

    # Infra
    "kec": "KEC.NS",
    "kalpataru": "KALPATARU.NS",
    "pnc infra": "PNCINFRA.NS",
    "hg infra": "HGINFRA.NS",
    "dilip buildcon": "DBL.NS",
    "kpl": "KPL.NS",
    "ashoka buildcon": "ASHOKA.NS",
    "sadbhav": "SADBHAV.NS",
    "irb": "IRB.NS",
    "gr infra": "GRINFRA.NS",
    "techno electric": "TECHNO.NS",

    # Manufacturing PLI
    "dixon": "DIXON.NS",
    "amber": "AMBER.NS",
    "syrma": "SYRMA.NS",
    "kaynes": "KAYNES.NS",
    "cyient": "CYIENT.NS",
    "netweb": "NETWEB.NS",
    "sfoorti": "SFOORTI.NS",
    "valiant": "VALIANT.NS",
    "emi": "EMI.NS",
    "avalon": "AVALON.NS",

    # Chemicals
    "navin fluor": "NAVINFLUOR.NS",
    "gujarat fluor": "GUJFLUORO.NS",
    "pi industries": "PIIND.NS",
    "srf": "SRF.NS",
    "aarti": "AARTIIND.NS",
    "vinati": "VINATIORGA.NS",
    "deepak nitrite": "DEEPAKNTR.NS",
    "alkyl amine": "ALKYLAMINE.NS",
    "clean science": "CLEAN.NS",
    "fine organic": "FINEORG.NS",
    "manali petro": "MANALIPETC.NS",
    "ghcl": "GHCL.NS",

    # Logistics
    "delhivery": "DELHIVERY.NS",
    "blue dart": "BLUEDART.NS",
    "gati": "GATI.NS",
    "tci": "TCI.NS",
    "vrl": "VRL.NS",
    "mahindra logistics": "MAHLOG.NS",
    "allcargo": "ALLCARGO.NS",

    # Consumer / Others
    "bajaj electricals": "BAJAJELEC.NS",
    "bajaj elec": "BAJAJELEC.NS",
    "orient electric": "ORIENTELEC.NS",
    "delta corp": "DELTACORP.NS",
    "delta": "DELTACORP.NS",
    "rajesh exports": "RAJESHEXPO.NS",
    "rajesh expo": "RAJESHEXPO.NS",
    "coastal corporation": "COASTCORP.NS",
    "tarsons": "TARSONS.NS",
    "tarsons products": "TARSONS.NS",
    "jtekt india": "JTEKTINDIA.NS",
    "jtekt": "JTEKTINDIA.NS",
    "spic": "SPIC.NS",
    "southern petrochemical": "SPIC.NS",
    
    # New additions - Infrastructure
    "dilip buildcon": "DBL.NS",
    "hg infra engineering": "HGINFRA.NS",
    "hg infra": "HGINFRA.NS",
    "kalpataru power": "KALPATARU.NS",
    "pnc infratech": "PNCINFRA.NS",
    
    # New additions - Consumer
    "vst industries": "VSTIND.NS",
    "vst": "VSTIND.NS",
    
    # New additions - Chemicals
    "manali petrochemicals": "MANALIPETC.NS",
    
    # New additions - Manufacturing
    "jtekt india limited": "JTEKTINDIA.NS",
    "tarsons products limited": "TARSONS.NS",

    # Defence
    "bel": "BEL.NS",
    "bharat electronics": "BEL.NS",
    "hal": "HAL.NS",
    "hindustan aeronautics": "HAL.NS",
    "bharat dynamics": "BDL.NS",
    "bdl": "BDL.NS",
    "ordnance factory": "OFB.NS",
    "ofb": "OFB.NS",
    "advanced weapons": "AWEIL.NS",
    "reliance defence": "RDLS.NS",
    "tata advanced systems": "TASL.NS",
    "larsen toubro defence": "LT.NS",
    "boeing india": "BOEING.NS",
    "merlinhawk aerospace": "MERLINHAWK.NS",
    "godrej aerospace": "GODREJPROP.NS",
    "jnk india": "JNKINDIA.NS",
    "jnk": "JNKINDIA.NS",

    # Large-cap names that appear in news
    "indus towers": "INDUSTOWER.NS",
    "ntpc": "NTPC.NS",
    "ncc": "NCC.NS",
    "ircon": "IRCON.NS",
    "railtel": "RAILTEL.NS",
    "sadbhav": "SADBHAV.NS",

    # More manufacturing
    "dixon technologies": "DIXON.NS",
    "kaynes technology": "KAYNES.NS",
    "netweb technologies": "NETWEB.NS",
    "syrma sgs": "SYRMA.NS",

    # More renewables
    "waaree energies": "WAAREE.NS",
    "suzlon energy": "SUZLON.NS",
    "inox wind": "INOXWIND.NS",
    "olectra greentech": "OLECTRA.NS",

    # More EV
    "jbm auto": "JBMA.NS",
    "exide industries": "EXIDEIND.NS",
    "amara raja": "AMARAJABAT.NS",

    # More chemicals
    "navin fluorine": "NAVINFLUOR.NS",
    "gujarat fluorocem": "GUJFLUORO.NS",
    "deepak nitrite": "DEEPAKNTR.NS",
    "vinati organics": "VINATIORGA.NS",

    # More infra
    "kec international": "KEC.NS",
    "kalpataru power": "KALPATARU.NS",
    "pnc infratech": "PNCINFRA.NS",
    "hg infra engineering": "HGINFRA.NS",
    "dilip buildcon": "DBL.NS",
    "ashoka buildcon": "ASHOKA.NS",

    # More pharma
    "dr reddy": "DRREDDY.NS",
    "cipla": "CIPLA.NS",
    "laurus labs": "LAURUS.NS",
    "granules india": "GRANULES.NS",

    # More IT
    "persistent systems": "PERSISTENT.NS",
    "cyient": "CYIENT.NS",
    "coforge": "COFORGE.NS",
    "birlasoft": "BSOFT.NS",
}


class TickerMapper:
    """Maps company names from news to NSE tickers"""

    def __init__(self):
        self.universe = get_universe()
        self._build_lookup()

    def _build_lookup(self):
        """Build name -> ticker lookup from universe"""
        self.name_to_ticker = {}
        self.ticker_to_name = {}

        for ticker, stock in self.universe.items():
            # Primary name
            self.name_to_ticker[stock.name.lower()] = ticker
            self.ticker_to_name[ticker] = stock.name

            # Add keywords
            for kw in stock.keywords:
                if len(kw) > 3:
                    self.name_to_ticker[kw.lower()] = ticker

            # Ticker base
            base = ticker.replace(".NS", "").replace(".BO", "").lower()
            self.name_to_ticker[base] = ticker

        # Add known aliases
        self.name_to_ticker.update({k.lower(): v for k, v in TICKER_ALIASES.items()})

    def resolve(self, name: str) -> Optional[str]:
        """Resolve a company name to ticker"""
        name = name.strip().lower()

        # Direct match
        if name in self.name_to_ticker:
            return self.name_to_ticker[name]

        # Try fuzzy match
        matches = get_close_matches(name, self.name_to_ticker.keys(), n=1, cutoff=0.85)
        if matches:
            return self.name_to_ticker[matches[0]]

        return None

    def resolve_multiple(self, names: List[str]) -> Dict[str, str]:
        """Resolve multiple names"""
        return {name: self.resolve(name) for name in names if self.resolve(name)}

    def extract_from_text(self, text: str) -> Dict[str, str]:
        """Extract all known company mentions from text"""
        found = {}
        text_lower = text.lower()
        
        # Sort names by length (longest first) to match more specific names first
        sorted_names = sorted(self.name_to_ticker.keys(), key=len, reverse=True)

        # Check all known names with word boundary matching
        import re
        for name in sorted_names:
            if len(name) < 4:
                continue
            ticker = self.name_to_ticker[name]
            if ticker in found:
                continue
            
            # Use word boundary matching for short names, substring for long names
            if len(name) <= 6:
                # Short names need exact word match (e.g., "india" shouldn't match "jtekt india")
                pattern = r'\b' + re.escape(name) + r'\b'
                if re.search(pattern, text_lower):
                    found[ticker] = self.ticker_to_name.get(ticker, name.title())
            else:
                # Long names can use substring match
                if name in text_lower:
                    found[ticker] = self.ticker_to_name.get(ticker, name.title())

        return found

    def get_company_info(self, ticker: str) -> Optional[dict]:
        """Get full company info from universe"""
        stock = self.universe.get(ticker)
        if stock:
            return {
                "ticker": stock.ticker,
                "name": stock.name,
                "sector": stock.sector,
                "price": stock.price,
                "market_cap_cr": stock.market_cap_cr,
                "avg_volume_lakh": stock.avg_volume_lakh,
                "keywords": stock.keywords
            }
        return None


# Global instance
_mapper: Optional[TickerMapper] = None


def get_mapper() -> TickerMapper:
    global _mapper
    if _mapper is None:
        _mapper = TickerMapper()
    return _mapper


def resolve_ticker(name: str) -> Optional[str]:
    return get_mapper().resolve(name)


def extract_tickers(text: str) -> Dict[str, str]:
    return get_mapper().extract_from_text(text)