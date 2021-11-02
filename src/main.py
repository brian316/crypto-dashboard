import asyncio
import json
import time
from typing import List

import aiohttp
import jwt
import pandas as pd
import seaborn as sns
import streamlit as st


async def get_risk(session, url) -> pd.DataFrame:
    async with session.get(url) as resp:
        data = await resp.json()
        if "data" in data:
            col_names = ["Price", "USD Risk"]
            df = pd.DataFrame(data["data"]["USD"], columns=col_names)
            df[col_names[1]] = df[col_names[1]].multiply(100)
            return df


async def get_metrics(names: list) -> List[pd.DataFrame]:
    try:
        token = st.secrets["TOKEN"]
        base_url = st.secrets["URL"]
        headers = {
            "Authorization": f"Bearer {token}",
        }
        async with aiohttp.ClientSession(headers=headers) as session:
            tasks = []
            for name in names:
                url = base_url + name
                tasks.append(asyncio.ensure_future(get_risk(session, url)))
            charts = await asyncio.gather(*tasks)
            return charts
    except Exception as e:
        return []


async def get_price_data(names: list) -> List[pd.DataFrame]:
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": ",".join(names),
        "vs_currencies": "USD",
        "include_24hr_change": "true",
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            return await resp.json()


def check_user_access() -> bool:
    try:
        encoded_jwt = jwt.decode(
            st.session_state.user_access_token,
            st.secrets["SECRET_KEY"],
            algorithms=["HS256"],
        )
        if encoded_jwt["exp"] >= int(time.time()):
            return True
        st.session_state.user_access_token = None
    except Exception as e:
        pass
    return False


def generate_user_access():
    encoded_jwt = jwt.encode(
        {"exp": time.time() + 99999999}, st.secrets["SECRET_KEY"], algorithm="HS256"
    )
    st.success("Successfully Created Token")
    return encoded_jwt


def user_message():
    if st.session_state.authenticated and st.session_state.callback:
        st.success("Successfully Authenticated")
        st.balloons()
    elif st.session_state.authenticated:
        return
    elif st.session_state.user_access_token and not st.session_state.callback:
        st.error("Invalid Token")
    elif not st.session_state.callback:
        st.warning("Please Authenticate")


def update_state(**kwargs):
    st.session_state.update(**kwargs)
    # defaults
    if "user_access_token" not in st.session_state:
        st.session_state.user_access_token = None
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "button_pressed" not in st.session_state:
        st.session_state.button_pressed = False
    if "callback" not in st.session_state:
        st.session_state.callback = False
    # check authenticated
    if (st.session_state.user_access_token and not st.session_state.authenticated) or (
        st.session_state.user_access_token and st.session_state.button_pressed
    ):
        st.session_state.authenticated = check_user_access()
    # send message
    if st.session_state.button_pressed:
        user_message()
    st.session_state.button_pressed = False
    st.session_state.callback = False
    # print(st.session_state)


async def main():
    update_state()
    with open("src/coins.json") as f:
        data = json.load(f)
        coins = data["coins"]
        ids = [coin["id"] for coin in coins]
    charts = await get_metrics(ids) if st.session_state.authenticated else []
    api_data = await get_price_data(ids)
    items_per_row = 3
    columns = st.columns(items_per_row)
    # color palette from seaborn
    cm = sns.color_palette("RdYlGn_r", as_cmap=True)
    for i, coin in enumerate(ids):
        with columns[i % items_per_row]:
            if not api_data[coin]:
                continue
            st.header(coins[i]["name"].title())
            st.metric(
                label="Price",
                value="${:,}".format(api_data[coin]["usd"]),
                delta="{:.2f}".format(api_data[coin]["usd_24h_change"]),
            )
            if charts and charts[i] is not None and st.session_state.authenticated:
                df = charts[i]
                with st.spinner(f"Loading {coin} Chart"):
                    index = max(
                        df.index[df["Price"] <= float(api_data[coin]["usd"])].tolist()
                    )
                    st.markdown(
                        f'<span style="font-family: Source Code Pro, monospace; font-size: .875rem;">Risk</span> `{"{:.2f}%".format(df["USD Risk"][index])}`',
                        unsafe_allow_html=True,
                    )
                    with st.expander("See Chart"):
                        df.set_index("Price", inplace=True)
                        st.dataframe(
                            df.style.background_gradient(
                                cmap=cm, low=0, high=0, subset=["USD Risk"]
                            ).format({"Price": "${:,}", "USD Risk": "{:.2f}%"})
                        )
            elif charts and charts[i] is None and st.session_state.authenticated:
                with st.container():
                    st.text("No Chart Data")
                    st.markdown("<br><br>", unsafe_allow_html=True)
    # authenticate
    user_access_token = st.text_input("api_key", type="password")
    st.session_state.button_pressed = st.button(
        "Authenticate",
        on_click=lambda: update_state(
            user_access_token=user_access_token, button_pressed=True, callback=True
        ),
    )  # update if successful
    update_state()  # update the bottm message


if __name__ == "__main__":
    st.set_page_config(
        page_title="Crypto Risks",
        page_icon=None,
        layout="centered",
        initial_sidebar_state="auto",
        menu_items=None,
    )
    with st.spinner("Loading Charts..."):
        asyncio.run(main())
