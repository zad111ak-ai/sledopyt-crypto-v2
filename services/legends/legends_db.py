"""
Исторические адреса — "Музей крипты".
Легендарные кошельки дляedu-контента.
"""
from dataclasses import dataclass


@dataclass
class Legend:
    address: str
    name: str
    owner: str
    chain: str
    year: int
    story: str
    balance: str
    significance: str  # legendary | important | infamous
    lesson: str


LEGENDS: dict[str, Legend] = {}

def _add(address: str, **kw):
    LEGENDS[address.lower()] = Legend(address=address, **kw)


_add(
    "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
    name="Genesis Block",
    owner="Satoshi Nakamoto",
    chain="bitcoin", year=2009,
    story="Первый BTC-адрес. Получил 50 BTC за genesis-блок. Никогда не трогал.",
    balance="~68 BTC",
    significance="legendary",
    lesson="Иногда бездействие — лучшая стратегия",
)

_add(
    "1XptgZD6hGJaBVX8RbZQFjGx9XnVYhP5c",
    name="Pizza Day",
    owner="Laszlo Hanyecz",
    chain="bitcoin", year=2010,
    story="10,000 BTC за 2 пиццы. Первая реальная BTC-транзакция.",
    balance="0 BTC",
    significance="legendary",
    lesson="Каждая транзакция — часть истории",
)

_add(
    "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
    name="Vitalik Buterin",
    owner="Vitalik Buterin",
    chain="ethereum", year=2015,
    story="Личный кошелёк создателя Ethereum. Использует для благотворительности.",
    balance="~$150M",
    significance="legendary",
    lesson="Создатели — тоже люди",
)

_add(
    "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe",
    name="Ethereum Foundation",
    owner="Ethereum Foundation",
    chain="ethereum", year=2014,
    story="Основной кошелёк фонда развития Ethereum.",
    balance="~$500M",
    significance="important",
    lesson="Институциональные деньги",
)

_add(
    "0xBE0eB53F46cd790Cd13851d5EFf43D12404d33E8",
    name="Binance Hot Wallet",
    owner="Binance Exchange",
    chain="ethereum", year=2017,
    story="Один из крупнейших hot wallets Binance.",
    balance="~$3B",
    significance="important",
    lesson="Не твои ключи — не твои монеты",
)

_add(
    "EQCD39VS5jcptHL8vMjEXrzGaRcCVYto7HUn4bpAOg8xqB2N",
    name="TON Foundation",
    owner="TON Foundation",
    chain="ton", year=2021,
    story="Официальный кошелёк TON Foundation.",
    balance="~1B TON",
    significance="important",
    lesson="От Telegram к глобальной сети",
)

_add(
    "1FeexV6bAHb8ybZjqQMjJrcCrHGW9sb6uF",
    name="Mt.Gox Hack",
    owner="Unknown (hacker)",
    chain="bitcoin", year=2011,
    story="Украдено 80,000 BTC с биржи Mt.Gox. Один из первых крупных хаков.",
    balance="~80,000 BTC",
    significance="infamous",
    lesson="Биржи могут быть взломаны",
)


def get_legend(address: str) -> Legend | None:
    return LEGENDS.get(address.lower())


def list_legends() -> list[Legend]:
    return list(LEGENDS.values())
