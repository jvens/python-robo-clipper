#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
import os

def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Split a large video file into match clips based on export from obs.vens.co."
    )
    parser.add_argument("--json", required=True, help="Path to the JSON file containing matches.")
    parser.add_argument("--video", required=True, help="Path to the video file.")
    parser.add_argument("--range", type=float, nargs=2, metavar=("START_NUM", "END_NUM"),
                        help="Optional inclusive range of match numbers to process.")
    parser.add_argument("--offset", type=float, required=True,
                        help="Global offset (in seconds) to align the video file with the event wall clock times.")
    parser.add_argument("--start", required=True,
                        help="Event key in JSON to use as the start of the clip (e.g. MATCH_START, SHOW_PREVIEW).")
    parser.add_argument("--end", required=True,
                        help="Event key in JSON to use as the end of the clip (e.g. MATCH_POST).")
    parser.add_argument("--startOffset", type=float, default=0,
                        help="Optional seconds to adjust the start event (can be negative). Default is 0.")
    parser.add_argument("--endOffset", type=float, default=0,
                        help="Optional seconds to adjust the end event (can be negative). Default is 0.")
    parser.add_argument("--out", required=True,
                        help="Output directory to store the generated videos. The directory will be created if it doesn't exist.")
    return parser.parse_args()

def load_json(json_file):
    with open(json_file, "r") as f:
        return json.load(f)

def filter_matches(matches, range_vals):
    if not range_vals:
        return matches
    start_num, end_num = range_vals
    return [m for m in matches if "number" in m and start_num <= m["number"] <= end_num]

def find_reference_time(matches, start_event):
    # Find the first match (lowest number) that contains the start_event key.
    sorted_matches = sorted(matches, key=lambda m: m.get("number", 0))
    for m in sorted_matches:
        if start_event in m:
            # Convert from ms to seconds.
            return m[start_event] / 1000
    return None

def run_ffmpeg(video_file, start_time, duration, output_file):
    cmd = [
        "ffmpeg",
        "-y",  # Overwrite output files without asking.
        "-i", video_file,
        "-ss", f"{start_time:.3f}",
        "-t", f"{duration:.3f}",
        "-c", "copy",
        output_file
    ]
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        print(f"Error processing {output_file}:\n{result.stderr}", file=sys.stderr)

def main():
    args = parse_arguments()

    # Check if the input files exist.
    if not os.path.isfile(args.json):
        print(f"JSON file {args.json} not found.", file=sys.stderr)
        sys.exit(1)
    if not os.path.isfile(args.video):
        print(f"Video file {args.video} not found.", file=sys.stderr)
        sys.exit(1)

    # Ensure the output directory exists.
    if not os.path.isdir(args.out):
        os.makedirs(args.out, exist_ok=True)

    # Load JSON data.
    data = load_json(args.json)
    if "matches" not in data:
        print("JSON file does not contain 'matches' list.", file=sys.stderr)
        sys.exit(1)
    matches = data["matches"]

    # Filter matches if --range is provided.
    filtered_matches = filter_matches(matches, args.range)

    if not filtered_matches:
        print("No matches found for the specified range.", file=sys.stderr)
        sys.exit(0)

    # Determine reference time using the first match with the required start event.
    ref_time = find_reference_time(filtered_matches, args.start)
    if ref_time is None:
        print(f"No matches in the specified range contain the start event key '{args.start}'.", file=sys.stderr)
        sys.exit(1)
    
    print(f"Reference event time (from first match with '{args.start}'): {ref_time:.3f} seconds")

    # Process each match
    for match in sorted(filtered_matches, key=lambda m: m.get("number", 0)):
        match_name = match.get("name", f"Match_{match.get('number', 'unknown')}")
        # Validate presence of both start and end events.
        if args.start not in match:
            print(f"Match {match_name} missing event {args.start}. Skipping")
            continue
        if args.end not in match:
            print(f"Match {match_name} missing event {args.end}. Skipping")
            continue

        # Convert event timestamps (from ms to seconds).
        start_event_time = match[args.start] / 1000
        end_event_time = match[args.end] / 1000

        # Compute video positions by aligning events to the video timeline.
        video_start_time = (start_event_time - ref_time) + args.offset + args.startOffset
        video_end_time   = (end_event_time - ref_time) + args.offset + args.endOffset

        duration = video_end_time - video_start_time

        if duration <= 0:
            print(f"Error: Invalid duration for match {match_name} (start: {video_start_time:.3f}, end: {video_end_time:.3f}). Skipping", file=sys.stderr)
            continue

        output_file = os.path.join(args.out, f"full-match-{match_name}.mkv")
        print(f"Processing match {match_name}:")
        print(f"  Start event time (wall clock): {start_event_time:.3f}s, video start: {video_start_time:.3f}s")
        print(f"  End event time (wall clock):   {end_event_time:.3f}s, video end:   {video_end_time:.3f}s")
        print(f"  Duration: {duration:.3f}s")
        
        run_ffmpeg(args.video, video_start_time, duration, output_file)

if __name__ == "__main__":
    main()
