import webbrowser

from django.shortcuts import render

from django.http.response import JsonResponse, HttpResponseRedirect
from rest_framework.parsers import JSONParser
from rest_framework import status
from enum import Enum
from django.shortcuts import redirect
from authenticate.models import User
from rest_framework.decorators import api_view
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication, BasicAuthentication
from rest_framework.response import Response
import requests
import os
import json
import secrets
import string
import pandas
import numpy
from base64 import b64encode

from dotenv import load_dotenv

load_dotenv()

from urllib.parse import urlencode
import base64
import datetime

from spotify.models import SpotifyTopArtistsLongTerm
from spotify.models import SpotifyTopArtistsMediumTerm
from spotify.models import SpotifyTopArtistsShortTerm
from spotify.models import SpotifyUser
from spotify.models import SpotifyRecentlyPlayed

# Client info
CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
REDIRECT_URI = os.getenv('SPOTIFY_REDIRECT_URI')

# Spotify API endpoints
AUTH_URL = 'https://accounts.spotify.com/authorize'
TOKEN_URL = 'https://accounts.spotify.com/api/token'
ME_URL = 'https://api.spotify.com/v1/me'

FRONTEND_URI = 'http://localhost:3000/setup/'

# API STATS ENDPOINTS
RECENTLY_PLAYED = 'https://api.spotify.com/v1/me/player/recently-played'
TOP_ARTISTS = 'https://api.spotify.com/v1/me/top/artists?limit=20&time_range='


@api_view(['POST'])
def top_artist_long(request):
    top_artist_helper_method(request, 'long', SpotifyTopArtistsLongTerm)
    return Response({'artist_all_time': 'Success'})


@api_view(['POST'])
def top_artist_medium(request):
    top_artist_helper_method(request, 'medium', SpotifyTopArtistsMediumTerm)
    return Response({'artist_6_months': 'Success'})


@api_view(['POST'])
def top_artist_short(request):
    top_artist_helper_method(request, 'short', SpotifyTopArtistsShortTerm)
    return Response({'artist_4_weeks': 'Success'})


def top_artist_helper_method(request, length, model):
    email = request.data.get('email')
    try:
        SpotifyUser.objects.get(email=email)
        spotify_user_model = SpotifyUser.objects.get(email=email)
        access_token = spotify_user_model.access_token

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": "Bearer {token}".format(token=access_token)
        }

        call_type = TOP_ARTISTS + length + '_term'
        r = requests.get(call_type, headers=headers)
        data = r.json()

        try:
            spotify_deleted = model.objects.filter(user=spotify_user_model.id).delete()
            print("DELETED STUFF ", spotify_deleted)

        except model.DoesNotExist:
            print("User has no top artists in the DB")

        artist_names = []
        images = []
        artist_urls = []
        artist_ids = []

        if not data.items:
            return Response({'message': "No Top Artists"})

        for song in data["items"]:
            artist_names.append(song["name"])
            images.append(song["images"][1]["url"])
            artist_urls.append(song["external_urls"]["spotify"])
            artist_ids.append(song["id"])

            try:
                model.objects.get(artist_id=song["id"]).delete()

            except model.DoesNotExist:
                print("No OLD Artist")

            spotify_top_artists = model.objects.create(user=spotify_user_model,
                                                       artist_name=song["name"],
                                                       artist_url=song["external_urls"][
                                                           "spotify"],
                                                       artist_id=song["id"],
                                                       image=song["images"][1]["url"]
                                                       )


        spotify_id = spotify_user_model.id
        top_artists = model.objects.filter(user_id=spotify_id)

        artists_list = []
        for artist in top_artists:
            response = {
                "artist_name": artist.artist_name,
                "image": artist.image,
                "artist_url": artist.artist_url,
                "artists_id": artist.artist_id
            }
            artists_list.append(response)

        return artists_list

    except model.DoesNotExist:
        return Response({"message": "Email is not in the DB"})


@api_view(['GET'])
def get_top_artist_long(request):
    artists = get_top_artist_helper_method(request, SpotifyTopArtistsLongTerm)
    return Response({'artist_all_time': artists})


@api_view(['GET'])
def get_top_artist_medium(request):
    artists = get_top_artist_helper_method(request, SpotifyTopArtistsMediumTerm)
    return Response({'artist_6_months': artists})


@api_view(['GET'])
def get_top_artist_short(request):
    artists = get_top_artist_helper_method(request, SpotifyTopArtistsShortTerm)
    return Response({'artist_4_weeks': artists})


def get_top_artist_helper_method(request, model):
    email = request.GET.get('email')

    if email is None:
        return Response({"err": "Email not provided"}, status=status.HTTP_406_NOT_ACCEPTABLE)

    spotify_user = SpotifyUser.objects.get(email=email)
    if spotify_user.email != email:
        return Response({"err": "invalid email"}, status=status.HTTP_406_NOT_ACCEPTABLE)

    spotify_id = spotify_user.id
    top_artists = model.objects.filter(user_id=spotify_id)

    artists_list = []
    for artist in top_artists:
        response = {
            "artist_name": artist.artist_name,
            "image": artist.image,
            "artist_url": artist.artist_url,
            "artists_id": artist.artist_id
        }
        artists_list.append(response)

    return artists_list


@api_view(['POST'])
def recently_played(request):
    email = request.data.get('email')

    try:
        spotify_user_model = SpotifyUser.objects.get(email=email)
        access_token = spotify_user_model.access_token

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": "Bearer {token}".format(token=access_token)
        }

        today = datetime.datetime.now()
        yesterday = today - datetime.timedelta(days=1)  # We want to run the feed daily, last 24 hours played songs
        yesterday_unix_timestamp = int(yesterday.timestamp()) * 1000

        r = requests.get(RECENTLY_PLAYED + '?limit=20&after={time}'.format(time=yesterday_unix_timestamp),
                         headers=headers)

        data = r.json()

        try:
            spotify_deleted = SpotifyRecentlyPlayed.objects.filter(user=spotify_user_model.id).delete()
            
        except SpotifyRecentlyPlayed.DoesNotExist:
            print("User has no previous playlists in the DB")

        song_titles = []
        artist_names = []
        played_at_list = []
        timestamps = []
        track_id = []
        images = []
        track_urls = []
        preview_urls = []

        if not data.items:
            return Response({'message': "No Recently Played Tracks"})

        for song in data["items"]:
            song_titles.append(song["track"]["name"])
            artist_names.append(song["track"]["album"]["artists"][0]["name"])
            played_at_list.append(song["played_at"])
            timestamps.append(song["played_at"][0:10])
            track_id.append(song["track"]["id"])
            images.append(song["track"]["album"]["images"][1]["url"])
            track_urls.append(song["track"]["external_urls"]["spotify"])
            preview_urls.append(song["track"]["preview_url"])

            try:
                SpotifyRecentlyPlayed.objects.get(track_id=song["track"]["id"]).delete()

            except SpotifyRecentlyPlayed.DoesNotExist:
                print("No OLD TRACKS")

            spotify_recently_played = SpotifyRecentlyPlayed.objects.create(user=spotify_user_model,
                                                                           song_title=song["track"]["name"],
                                                                           artist_name=
                                                                           song["track"]["album"]["artists"][0]["name"],
                                                                           played_at=song["played_at"][0:10],
                                                                           track_id=song["track"]["id"],
                                                                           image=song["track"]["album"]["images"][1][
                                                                               "url"],
                                                                           track_url=song["track"]["external_urls"][
                                                                               "spotify"],
                                                                           preview_url=song["track"]["preview_url"]
                                                                           )

       
        return Response({'message': data})

    except SpotifyUser.DoesNotExist:
        return Response({"message": "Email is not in the DB"})


@api_view(['GET'])
def get_recently_played(request):
    email = request.GET.get('email')

    if email is None:
        return Response({"err": "Email not provided"}, status=status.HTTP_406_NOT_ACCEPTABLE)

    spotify_user = SpotifyUser.objects.get(email=email)
    if spotify_user.email != email:
        return Response({"err": "invalid email"}, status=status.HTTP_406_NOT_ACCEPTABLE)

    spotify_id = spotify_user.id

    recent_tracks = SpotifyRecentlyPlayed.objects.filter(user_id=spotify_id)

    tracks = []
    for track in recent_tracks:
        response = {
            "user_id": track.user_id,
            "song_title": track.song_title,
            "artist_name": track.artist_name,
            "track_id": track.track_id,
            "played_at": track.played_at,
            "image": track.image,
            "track_url": track.track_url,
            "preview_url": track.preview_url
        }
        tracks.append(response)

    return Response({'recent_played': tracks}, status=status.HTTP_202_ACCEPTED)


@api_view(['GET'])
def spotify_login(request):
    # Redirect URI can be guessed, hence build a random state
    state = ''.join(
        secrets.choice(string.ascii_uppercase + string.digits) for _ in range(16)
    )
    scope = 'user-read-private user-read-email user-follow-read user-library-read user-read-recently-played ' \
            'user-top-read user-follow-read user-follow-modify playlist-read-private playlist-read-collaborative ' \
            'playlist-modify-public '

    payload = {
        'response_type': 'code',
        'client_id': os.environ.get('SPOTIFY_CLIENT_ID'),
        'scope': scope,
        'redirect_uri': REDIRECT_URI
    }

    res = HttpResponseRedirect(f'{AUTH_URL}/?{urlencode(payload)}')

    webbrowser.open(res.url)
    return Response({'message': "Returned token"}, status=status.HTTP_202_ACCEPTED)


@api_view(['GET'])
def spotify_callback(request):
    code = request.GET.get('code')
    if code is None:
        return redirect(FRONTEND_URI)

    # Request tokens with code we obtained
    auth_options = {
        'code': code,
        'redirect_uri': REDIRECT_URI,
        'grant_type': 'authorization_code',
    }

    # Post request in order to get callback URL
    res = requests.post(TOKEN_URL, auth=(CLIENT_ID, CLIENT_SECRET), data=auth_options)

    res_data = res.json()
    access_token = res_data.get('access_token')
    refresh_token = res_data.get('refresh_token')

    if res_data.get('error') or res.status_code != 200:
        Response({"Failed to receive token: %s "},
                 res_data.get('error', 'No error information received.'))

    # Getting user's information
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": "Bearer {token}".format(token=access_token)
    }

    r = requests.get(ME_URL, headers=headers)
    user_data = r.json()

    if r.status_code != 200:
        Response({"Failed to get Profile info %s "},
                 user_data.get('error', 'No error message returned.'))

    # Update DB if any of the user info has changed
    user_ID = user_data['id']

    if not user_data['images']:
        user_data['images'] = ''

    try:
        spotify_user_info = SpotifyUser.objects.get(id=user_data['id'])
        spotify_user_info.access_token = access_token
        spotify_user_info.refresh_token = refresh_token
        spotify_user_info.save()
    except SpotifyUser.DoesNotExist:
        if (user_data['images']):
            spotify_user_model = SpotifyUser.objects.create(country=user_data['country'],
                                                            display_name=user_data['display_name'],
                                                            id=user_data['id'], href=user_data['href'],
                                                            followers=user_data['followers']['total'],
                                                            image=user_data['images'][0]['url'],
                                                            access_token=access_token,
                                                            refresh_token=refresh_token)
        else:
            spotify_user_model = SpotifyUser.objects.create(country=user_data['country'],
                                                            display_name=user_data['display_name'],
                                                            id=user_data['id'], href=user_data['href'],
                                                            followers=user_data['followers']['total'],
                                                            image="",
                                                            access_token=access_token,
                                                            refresh_token=refresh_token)

        redirect(FRONTEND_URI + '?access_token=' + access_token + '&id=' + user_ID)

    return redirect(FRONTEND_URI + '?access_token=' + access_token + '&id=' + user_ID)


@api_view(['POST', 'GET'])
def get_spotify_update_email(request):
    # UPDATE EMAIL IF THEY DONT HAVE
    email = request.data.get('email')
    id = request.data.get('id')

    if email is None:
        return Response({"err": "Email not provided"}, status=status.HTTP_406_NOT_ACCEPTABLE)

    spotify_user_info = SpotifyUser.objects.get(id=id)
    if spotify_user_info is None:
        return Response({"err": "User not found"}, status=status.HTTP_404_NOT_FOUND)

    spotify_user_info.email = email
    spotify_user_info.save()

    user_spotify_info = {
        'id': spotify_user_info.id,
        'country': spotify_user_info.country,
        'display_name': spotify_user_info.display_name,
        'email': spotify_user_info.email,
        'href': spotify_user_info.href,
        'followers': spotify_user_info.followers,
        'image': spotify_user_info.image
    }
    return Response({"user": user_spotify_info}, status=status.HTTP_202_ACCEPTED)


@api_view(['GET'])
def spotify_me(request):
    email = request.GET.get('email')
    if email is None:
        return Response({"err": "Email not provided"}, status=status.HTTP_406_NOT_ACCEPTABLE)

    spotify_user_info = SpotifyUser.objects.get(email=email)

    if spotify_user_info.email != email:
        return Response({"err": "invalid email"}, status=status.HTTP_406_NOT_ACCEPTABLE)

    user_spotify_info = {
        'id': spotify_user_info.id,
        'country': spotify_user_info.country,
        'display_name': spotify_user_info.display_name,
        'email': spotify_user_info.email,
        'href': spotify_user_info.href,
        'followers': spotify_user_info.followers
    }
    return Response({"user": user_spotify_info}, status=status.HTTP_202_ACCEPTED)


def get_credentials():
    return b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode(
        "ascii"
    )


@api_view(['POST'])
def spotify_refresh(request):
    # Refreshes access token
    email = request.data.get('email')
    spotify_user = SpotifyUser.objects.get(email=email)
    refresh_token = spotify_user.refresh_token

    client_creds_b64 = get_credentials()

    payload = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token
    }
    headers = {"Authorization": f"Basic {client_creds_b64}"}

    res = requests.post(
        TOKEN_URL, data=payload, headers=headers
    )
    res_data = res.json()
    new_access_token = res_data["access_token"]

    spotify_user.access_token = new_access_token
    spotify_user.save()

    return Response({"Response Data ": res_data}, status=status.HTTP_202_ACCEPTED)
