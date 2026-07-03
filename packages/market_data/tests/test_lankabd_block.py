"""LankaBD block-market parser — offline unit tests on real page markup."""

from __future__ import annotations

import datetime as dt

from bulls.market_data.providers.lankabd import parse_block_market

# Trimmed from the live page (2026-07-03 fetch): date input + DSE pane row + CSE pane row.
FIXTURE = """
<input type="text" id="searchDate" value="2026-07-02" />
<div class="tab-pane active" id="dse">
<table><tbody>
  <tr>
    <td class="black-text">
      <a class="indigo-text" href="/Company/OverviewV2?cid=41&sn=UTTARABANK&cn=Uttara_Bank_PLC">UTTARABANK</a>
      <span class="fontRobo float-right" title="Market Depth"><a href="/Home/MarketDepth?mktDepthSymbol=UTTARABANK"><i class="fas fa-database"></i></a></span>
    </td>
    <td class="text-right">150,000</td>
    <td class="text-right">2.970</td>
    <td class="text-right">1</td>
    <td class="text-right">19.80</td>
    <td class="text-right">19.80</td>
  </tr>
  <tr>
    <td class="black-text"><a class="indigo-text" href="/Company/OverviewV2?cid=9&sn=BEXIMCO&cn=B">BEXIMCO</a></td>
    <td class="text-right">1,850,000</td>
    <td class="text-right">222.15</td>
    <td class="text-right">3</td>
    <td class="text-right">120.50</td>
    <td class="text-right">119.90</td>
  </tr>
</tbody></table>
</div>
<div class="tab-pane" id="cse">
<table><tbody>
  <tr>
    <td class="black-text"><a class="indigo-text" href="/Company/OverviewV2?cid=99&sn=CSEONLY&cn=X">CSEONLY</a></td>
    <td class="text-right">5,000</td>
    <td class="text-right">0.100</td>
    <td class="text-right">1</td>
    <td class="text-right">20.00</td>
    <td class="text-right">20.00</td>
  </tr>
</tbody></table>
</div>
"""


def test_parses_dse_rows_only() -> None:
    rows = parse_block_market(FIXTURE)
    assert [r.code for r in rows] == ["UTTARABANK", "BEXIMCO"]  # CSE pane excluded


def test_row_fields() -> None:
    r = parse_block_market(FIXTURE)[1]
    assert r.trade_date == dt.date(2026, 7, 2)
    assert r.quantity == 1_850_000
    assert r.value_mn == 222.15
    assert r.trades == 3
    assert r.max_price == 120.5 and r.min_price == 119.9


def test_no_date_means_no_rows() -> None:
    """Freshness-honesty: a page without a parsable date yields nothing rather than a guess."""
    assert parse_block_market(FIXTURE.replace('value="2026-07-02"', 'value=""')) == []


def test_rejects_degenerate_rows() -> None:
    """A malformed row (zero quantity/value, or min price above max) is a parse error, not a
    real block trade — reject it rather than storing garbage for the admin view."""
    bad = FIXTURE.replace(
        '<td class="text-right">1,850,000</td>', '<td class="text-right">0</td>', 1
    )
    rows = parse_block_market(bad)
    assert [r.code for r in rows] == ["UTTARABANK"]  # the zero-quantity BEXIMCO row is dropped
