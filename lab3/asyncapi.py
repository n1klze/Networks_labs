import asyncio
import json
import requests
from tqdm import tqdm

LOCATIONS_URL         = "https://graphhopper.com/api/1/geocode"
WEATHER_URL           = "https://api.openweathermap.org/data/2.5/weather"
PLACES_URL            = "http://api.opentripmap.com/0.1/en/places/radius"
PLACE_DESC_URL        = "http://api.opentripmap.com/0.1/en/places/xid/"
_locale               = "en"
_max_num_of_locations = 10
_radius               = 500


class Main:
    def __init__(self, place: str):
        self.place = place

    def get_locations(self):
        query = {
            "q"     : self.place,
            "locale": _locale,
            "limit" : _max_num_of_locations,
            "key"   : "a34be09b-4ec3-4732-bc9b-889734daa59d",
        }

        response = requests.get(LOCATIONS_URL, params=query).json()
        locations = response["hits"]

        return locations

    async def main(self):
        locations = self.get_locations()

        for num, location in zip(range(1, len(locations) + 1), locations):
            print(
                num,
                ". ",
                location.get("country"),
                ", {}".format(state) if (state := location.get("state")) else "",
                ", {}".format(city) if (city := location.get("city")) else "",
                ", {}".format(street) if (street := location.get("street")) else "",
                ", {}".format(housenumber)
                if (housenumber := location.get("housenumber"))
                else "",
                ", {}".format(postcode)
                if (postcode := location.get("postcode"))
                else "",
                " — ",
                location.get("osm_value").replace("_", " "),
                " ",
                location.get("name"),
                sep="",
            )

        location_num = int(input("Choose location: "))
        chosen_location = locations[location_num - 1]

        weather = await self.get_weather(chosen_location)
        points_of_interests = await self.get_points_of_interests(chosen_location)

        print(
            "-" * 30,
            "\nTemperature °C:",
            weather["main"]["temp"],
            "\nFeels like °C:",
            weather["main"]["feels_like"],
            "\nWind speed m/s:",
            weather["wind"]["speed"],
            "\nDescription:",
            weather["weather"][0]["description"],
            "\n{}\n".format("-" * 30),
        )
        for name, info in points_of_interests.items():
            address = info.get("address")
            print(
                name,
                ":\nAddress: ",
                country if (country := address.get("country")) else "",
                ", {}".format(state) if (state := address.get("state")) else "",
                ", {}".format(county) if (county := address.get("county")) else "",
                ", {}".format(city) if (city := address.get("city")) else "",
                ", {}".format(town) if (town := address.get("town")) else "",
                ", {}".format(state_district)
                if (state_district := address.get("state_district"))
                else "",
                ", {}".format(suburb) if (suburb := address.get("suburb")) else "",
                ", {}".format(road) if (road := address.get("road")) else "",
                ", {}".format(house_number)
                if (house_number := address.get("house_number"))
                else "",
                ", {}".format(house) if (house := address.get("house")) else "",
                ", {}".format(postcode)
                if (postcode := address.get("postcode"))
                else "",
                "\nDescription: ",
                info["info"]["descr"]
                if info.get("info")
                else (
                    info["wikipedia_extracts"]["text"]
                    if info.get("wikipedia_extracts")
                    else "—//—"
                ),
                "\n",
                sep="",
            )

    async def get_weather(self, location):
        query = {
            "lat"  : location.get("point").get("lat"),
            "lon"  : location.get("point").get("lng"),
            "units": "metric",
            "appid": "7fc197d7c76210f391b24d66daa8405c",
        }

        response = requests.get(WEATHER_URL, params=query).json()
        return response

    async def get_description(self, xid):
        response = requests.get(
            "{0}{1}?apikey=5ae2e3f221c38a28845f05b660d961e5446b2194b3baa617ba6bba2b".format(
                PLACE_DESC_URL, xid
            )
        ).json()
        return response

    async def get_points_of_interests(self, location):
        query = {
            "lang"  : _locale,
            "radius": _radius,
            "lat"   : location.get("point").get("lat"),
            "lon"   : location.get("point").get("lng"),
            "apikey": "5ae2e3f221c38a28845f05b660d961e5446b2194b3baa617ba6bba2b",
        }

        response = requests.get(PLACES_URL, params=query).json()
        points = response["features"]
        points_of_interests = {}

        for point in tqdm(points):
            properties = point["properties"]
            points_of_interests[properties["name"]] = await self.get_description(
                properties["xid"]
            )

        return points_of_interests


if __name__ == "__main__":
    place = input("Enter place: ")

    app = Main(place)
    asyncio.run(app.main())
