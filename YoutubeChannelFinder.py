from ast import Dict
from ctypes import Array
from math import floor
from googleapiclient.discovery import build, HttpError
from datetime import datetime, timezone, timedelta
from tqdm import tqdm
import os

API_KEY = ""

def get_boolean_input(prompt="Enter 'yes' or 'no': "):
    user_input = input(prompt).strip().lower()  # Get user input and normalize it
    if user_input in ('yes', 'y', 'true', 't'):
        return True
    elif user_input in ('no', 'n', 'false', 'f'):
        return False
    else:
        print("Invalid input. Please enter 'yes' or 'no'.")
        return get_boolean_input(prompt)  # Prompt again if input is invalid


def save(api_key, filename="config.txt"):
    """
    Saves the directory and API key to a text file.
    
    Parameters:
    - api_key (str): The API key to save.
    - filename (str): The name of the text file to save the information.
    """

    try:
        with open(filename, "w", encoding="utf-8") as file:
            file.write(f"API Key: {api_key}\n")
        print(f"Configuration saved successfully to {filename}")
    except Exception as e:
        print(f"An error occurred while saving the configuration: {e}")

def load(filename="config.txt"):
    """
    Loads the API key from a text file.
    
    Parameters:
    - filename (str): The name of the text file to read the information from.

    Returns:
    - string - the API key
    """
    try:
        with open(filename, "r", encoding="utf-8") as file:
            lines = file.readlines()
            api_line = lines[0].strip().split(": ")[1]
            if api_line != "[PASTE API KEY HERE]":
                use_saved_key = get_boolean_input(f"Used saved key? ({api_line} (Y/N): ")
                if use_saved_key:
                    api = api_line  # Extract API Key
                else:
                    api = input("Enter your Youtube API Key: ")
            else:
                api = input("Enter your Youtube API Key: ")
            return api
    except Exception as e:
         print(f"An error occurred while loading the configuration: {e}")
         return None, None

def file_exists(file_path):
    return os.path.isfile(file_path)


if file_exists("config.txt"):
    API_KEY = load("config.txt")
    youtube = build('youtube', 'v3', developerKey=API_KEY)
    save(API_KEY)
else:
    API_KEY = input("Enter your Youtube API Key:")
    save(API_KEY)
    youtube = build('youtube', 'v3', developerKey=API_KEY)

# Define quota costs
quota_costs = {
    'search': 100,
    'channels_list': 1,
    'playlistItems': 1,
}

# Dictionary to track usage
quota_usage = {
    'search': 0,
    'channels_list': 0,
    'playlistItems': 0,
}

def track_usage(api_call_type):
    """Tracks the usage of each API call type based on predefined costs."""
    if api_call_type in quota_costs:
        quota_usage[api_call_type] += quota_costs[api_call_type]

def get_channels_for_game_with_subscribers(game_names, min_subscribers, max_subscribers, max_results=50):
    channels = {}
    processed_channel_ids = set()  # Cache to avoid processing duplicates
    query = " | ".join(game_names)
    try:
        # Perform a single search for combined game names
        search_response = youtube.search().list(
            part='snippet',
            q=query,
            type='video',
            maxResults=min(max_results, 50)  # Keep requests limited
        ).execute()

        track_usage('search')

        # Collect unique channel IDs from the search results
        unique_channel_ids = {item['snippet']['channelId'] for item in search_response.get('items', [])}

        # Check if we need to paginate
        while 'nextPageToken' in search_response and len(unique_channel_ids) < max_results:
            search_response = youtube.search().list(
                part='snippet',
                q=query,
                type='video',
                maxResults=min(max_results - len(unique_channel_ids), 50),
                pageToken=search_response['nextPageToken']
            ).execute()
            unique_channel_ids.update(item['snippet']['channelId'] for item in search_response.get('items', []))
            track_usage('search')

        unique_channel_ids = list(unique_channel_ids)[:max_results]  # Limit to max_results

        # Retrieve channels in batches of 50, filtering by subscribers
        for i in tqdm(range(0, len(unique_channel_ids), 50), desc="Processing channels"):
            batch = [ch_id for ch_id in unique_channel_ids[i:i + 50] if ch_id not in processed_channel_ids]
            channel_response = youtube.channels().list(
                part='snippet,statistics',
                id=','.join(batch)
            ).execute()
            track_usage('channels_list')

            for item in channel_response.get('items', []):
                subscriber_count = int(item['statistics'].get('subscriberCount', 0))
                if min_subscribers <= subscriber_count <= max_subscribers:
                    channel_id = item['id']
                    view_count = int(item['statistics'].get('viewCount', 0))
                    video_count = int(item['statistics'].get('videoCount', 0))
                    if video_count > 0:
                        average_views_per_video = view_count / video_count
                    else:
                        average_views_per_video = 0  # Handle case where there are no videos

                    if channel_id not in channels:
                        channels[channel_id] = {
                            'title': item['snippet']['title'],
                            'subscriber_count': subscriber_count,
                            'average_views': floor(average_views_per_video)
                        }
                    processed_channel_ids.add(channel_id)  # Add to processed set
    except HttpError as e:
        # Check for quota limit error
        if e.resp.status == 403 and 'quota' in e.error_details:
            print("Error: You have exceeded your YouTube API quota. Please try again later.")
        else:
            print(f"An error occurred: {e}")

    return channels

def display_in_legible_form(channels: Dict, filename="channels_info.md", kw = []):
    full_path = f"{filename}"
    sorted_channels = sorted(channels.items(), key=lambda item: item[1]['average_views'], reverse=True) # Sort the channels based on average number of views

    with open(full_path, "w", encoding="utf-8") as file:
        file.write("# YouTube Channels\n\n")  # Title
        file.write("**Keywords Searched For:**\n")
        file.write(", ".join(kw) + "\n\n")  # Join keywords with commas and write them
        file.write("| Reviewed | Channel Name | Subscribers | Average Views |\n")  # Header
        file.write("|------|--------------|-------------|-------------|\n")  # Separator

        for channel_id, info in sorted_channels:
            url = f"https://www.youtube.com/channel/{channel_id}"
            formatted_avg_views = f"{info['average_views']:,}"
            formatted_subs = f"{info['subscriber_count']:,}"
            # Write each channel's information in Markdown table format with a task checkbox
            file.write(f"| [] | [{info['title']}]({url}) | {formatted_subs} | {formatted_avg_views} |\n")

            # print to console for verification
            print(f"{info['title']} (https://www.youtube.com/channel/{channel_id}, Subscribers: {info['subscriber_count']}, Average Views: {info['average_views']})\n")
    print(f"List of channels created at: {full_path}")

def display_quota_usage():
    total_usage = sum(quota_usage.values())
    print("Quota Usage Summary:")
    for call_type, usage in quota_usage.items():
        print(f" - {call_type}: {usage} units")
    print(f"Total Quota Used: {total_usage} units")

def get_keywords_from_list(inputwords):
    kw = inputwords.split(', ')
    return kw

def get_subs_from_range(inputrange):
    mins = inputrange.split('-')[0]
    maxs = inputrange.split('-')[1]
    return int(mins), int(maxs)

current_time = datetime.now(timezone.utc)
formatted_time = str(current_time.strftime("%Y%m%d%H%M%S%Z"))

keywords = get_keywords_from_list(input("Enter your keywords, each separated by a ', ' Comma + Space: "))

minsubs, maxsubs = get_subs_from_range(input("Enter subscriber range in this format 'min-max' (E.g 50-3000): "))
maxr = int(input("What is the maximum number of channels to be returned? "))

if minsubs > maxsubs:
    minsubs = maxsubs

channels_data = get_channels_for_game_with_subscribers(keywords, minsubs, maxsubs, max_results=maxr)
display_in_legible_form(channels_data, f"{formatted_time}.md", keywords)
display_quota_usage()
input("Press any key to exit...")