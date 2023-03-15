# The MIT License (MIT)
# 
# Copyright (c) 2022-2023 Péter Tombor.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from datetime import datetime
from string import Template
from typing import List

from ..ItchGame import ItchGame

DATE_FORMAT = '<span>%Y-%m-%d</span> <span>%H:%M</span>'
ROW_TEMPLATE = Template("""<tr>
        <td>$name</td>
        <td style="text-align:center">$sale_date</td>
        <td style="text-align:center" title="$claimable_text">$claimable_icon</td>
        <td><a href="$url" title="URL">&#x1F310;</a></td>
        <td><a href="./data/$id.json" title="JSON data">&#x1F4DC;</a></td>
    </tr>""")

def generate_html(games: List[ItchGame]):
    with open('ItchClaim/web/template.html', 'r') as f:
        template = Template(f.read())
    games.sort(key=lambda a: (-1*a.sales[-1].id, a.name))

    # filter active sales
    active_sales = list(filter(lambda game: game.is_sale_active, games))
    active_sales_rows = generate_rows(active_sales)

    upcoming_sales = list(filter(lambda game: game.is_sale_upcoming, games))
    upcoming_sales_rows = generate_rows(upcoming_sales)

    return template.substitute(
            active_sales_rows = '\n'.join(active_sales_rows),
            upcoming_sales_rows = '\n'.join(upcoming_sales_rows),
            last_update = datetime.now().strftime(DATE_FORMAT),
        )

def generate_rows(games: List[ItchGame]) -> List[str]:
    rows: List[str] = []
    for game in games:
        if game.claimable == False:
            claimable_text = 'Not claimable'
            claimable_icon = '&#x274C;'
        elif game.claimable == True:
            claimable_text = 'claimable'
            claimable_icon = '&#x2714;'
        else:
            claimable_text = 'Unknown'
            claimable_icon = '&#x1F551;'
        
        sale_date = game.sales[-1].end if game.sales[-1].end else game.sales[-1].start

        rows.append(ROW_TEMPLATE.substitute(
            name = game.name,
            sale_date = sale_date.strftime(DATE_FORMAT),
            claimable_text = claimable_text,
            claimable_icon = claimable_icon,
            url = game.url,
            id = game.id,
        ))
    return rows