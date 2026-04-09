"""SpendCube currency conversion and FX rate handling."""

import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd


class CurrencyConverter:
    """Converts transaction amounts between currencies using bundled FX rate table."""

    def __init__(self, fx_rates_path: str, base_currency: str = 'AUD') -> None:
        self.base_currency = base_currency
        self._rates: dict[tuple[str, str, str], float] = {}
        self._pair_months: dict[tuple[str, str], list[str]] = {}
        self._load_rates(fx_rates_path)

    def _load_rates(self, fx_rates_path: str) -> None:
        with open(fx_rates_path, newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = (row['from_ccy'], row['to_ccy'], row['year_month'])
                self._rates[key] = float(row['rate'])
                pair = (row['from_ccy'], row['to_ccy'])
                if pair not in self._pair_months:
                    self._pair_months[pair] = []
                self._pair_months[pair].append(row['year_month'])

    def _year_month_str(self, d: date) -> str:
        return f'{d.year}-{d.month:02d}'

    def _month_ordinal(self, ym: str) -> int:
        year, month = ym.split('-')
        return int(year) * 12 + int(month)

    def _find_nearest_month(self, pair: tuple[str, str], year_month: str) -> str:
        months = self._pair_months[pair]
        target = self._month_ordinal(year_month)
        return min(months, key=lambda m: abs(self._month_ordinal(m) - target))

    def convert(
        self,
        amount: Decimal,
        from_ccy: str,
        transaction_date: date,
    ) -> tuple[Decimal, float | None, str | None]:
        if from_ccy == self.base_currency:
            return (amount, 1.0, None)

        pair = (from_ccy, self.base_currency)
        if pair not in self._pair_months:
            return (amount, None, f'UNKNOWN_CURRENCY_PAIR: {from_ccy}/{self.base_currency}')

        year_month = self._year_month_str(transaction_date)
        key = (from_ccy, self.base_currency, year_month)

        if key in self._rates:
            rate = self._rates[key]
            return (Decimal(str(rate)) * amount, rate, None)

        nearest = self._find_nearest_month(pair, year_month)
        rate = self._rates[(from_ccy, self.base_currency, nearest)]
        warning = f'RATE_ESTIMATE: used {nearest} rate for {year_month}'
        return (Decimal(str(rate)) * amount, rate, warning)

    def convert_dataframe(
        self,
        df: pd.DataFrame,
        amount_col: str,
        currency_col: str,
        date_col: str,
    ) -> pd.DataFrame:
        df = df.copy()
        base_amounts = []
        fx_rates = []
        fx_warnings = []
        for _, row in df.iterrows():
            amount = Decimal(str(row[amount_col]))
            from_ccy = str(row[currency_col])
            txn_date = row[date_col]
            if not isinstance(txn_date, date):
                txn_date = pd.to_datetime(txn_date).date()
            converted, rate, warning = self.convert(amount, from_ccy, txn_date)
            base_amounts.append(converted)
            fx_rates.append(rate)
            fx_warnings.append(warning)
        df['base_amount'] = base_amounts
        df['fx_rate_used'] = fx_rates
        df['fx_warning'] = fx_warnings
        return df


if __name__ == '__main__':
    fx_path = Path(__file__).parent.parent.parent / 'data' / 'reference' / 'fx_rates.csv'
    converter = CurrencyConverter(str(fx_path))

    samples = [
        (Decimal('8750.00'), 'USD', date(2024, 2, 12), 'DHL Express'),
        (Decimal('1500.00'), 'EUR', date(2024, 3, 15), 'Sample EUR'),
        (Decimal('5000.00'), 'GBP', date(2023, 6, 1), 'Sample GBP'),
        (Decimal('250000.00'), 'JPY', date(2024, 1, 20), 'Sample JPY'),
        (Decimal('1200.00'), 'AUD', date(2024, 2, 1), 'Sample AUD (base)'),
        (Decimal('999.00'), 'XYZ', date(2024, 2, 1), 'Unknown currency'),
        (Decimal('500.00'), 'USD', date(2030, 1, 1), 'Future date (nearest month)'),
    ]

    header = f"{'Description':<30} {'Orig':>12} {'CCY':<5} {'Date':<12} {'AUD':>14} {'Rate':>10}  Warning"
    print(header)
    print('-' * 105)
    for amount, ccy, txn_date, desc in samples:
        converted, rate, warning = converter.convert(amount, ccy, txn_date)
        rate_str = f'{rate:.6f}' if rate is not None else 'N/A     '
        warn_str = warning or ''
        print(f'{desc:<30} {amount:>12} {ccy:<5} {str(txn_date):<12} {float(converted):>14.2f} {rate_str:>10}  {warn_str}')

    # Verify DHL row
    dhl_converted, dhl_rate, dhl_warning = converter.convert(Decimal('8750.00'), 'USD', date(2024, 2, 12))
    print(f'\nVerification: DHL USD 8750.00 → AUD {float(dhl_converted):.2f} (rate: {dhl_rate})')
    assert 12000 <= float(dhl_converted) <= 15000, f'Expected 12000-15000 AUD, got {float(dhl_converted):.2f}'
    print('PASS: DHL conversion in expected range 12000-15000 AUD')
