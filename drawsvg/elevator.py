import math, os
import drawsvg as draw



W, H          = 600, 700
SHAFT_X       = 200          # left edge of shaft
SHAFT_W       = 160          # shaft width
CABIN_H       = 80           # cabin height
CABIN_PAD     = 6            # gap between cabin and shaft walls
DOOR_W        = (SHAFT_W - CABIN_PAD * 2) / 2  # each door half-width
FLOOR_H       = 100          # pixels per floor
BOTTOM_MARGIN = 80           # space below floor 0
NUM_FLOORS    = 6            # 0..5

# derived
SHAFT_TOP     = H - BOTTOM_MARGIN - NUM_FLOORS * FLOOR_H
SHAFT_BOTTOM  = H - BOTTOM_MARGIN
SHAFT_H       = SHAFT_BOTTOM - SHAFT_TOP


def _floor_y(floor):
    return SHAFT_BOTTOM - (floor + 1) * FLOOR_H


def _cabin_cy(floor):
    return _floor_y(floor) + (FLOOR_H - CABIN_H) / 2


def create_elevator_animation(start_floor=0, end_floor=4, speed=1.0):
    n_floors_travel = abs(end_floor - start_floor)
    if n_floors_travel == 0:
        n_floors_travel = 1
        end_floor = start_floor + 1

    max_floor = max(start_floor, end_floor, NUM_FLOORS - 1)
    num_floors = max_floor + 1

    DOOR_TIME   = 0.8          # open or close duration
    TRAVEL_PER  = 0.7          # seconds per floor of travel
    DWELL_START = 0.5          # doors-open dwell at start
    DWELL_END   = 1.0          # doors-open dwell at end
    REST        = 0.3          # padding at end

    travel_time = n_floors_travel * TRAVEL_PER
    total = DWELL_START + DOOR_TIME + travel_time + DOOR_TIME + DWELL_END + REST
    duration = total / speed

    # i didnt get the error from the pitman example here, so i didnt clamp it
    def t(sec):
        return sec / speed

    # key frames, scaled based on simulation speed
    # basically each t tells us a state of what is happinign.
    # we can map this to formal states... (even states are discrete states, odd are transitions) :D
    t0 = 0                                          # start: doors open
    t1 = t(DWELL_START)                             # doors begin closing
    t2 = t(DWELL_START + DOOR_TIME)                 # doors closed, travel starts
    t3 = t(DWELL_START + DOOR_TIME + travel_time)   # travel ends, doors open
    t4 = t(DWELL_START + DOOR_TIME + travel_time + DOOR_TIME)  # doors fully open
    t5 = duration                                   # end

    d = draw.Drawing(
        W, H,
        animation_config=draw.types.SyncedAnimationConfig(
            duration=duration,
            show_playback_progress=True,
            show_playback_controls=True,
        ),
    )

    d.append(draw.Rectangle(0, 0, W, H, fill="#e8e4de"))

    bldg_x = SHAFT_X - 60
    bldg_w = SHAFT_W + 120

    # building facade
    d.append(draw.Rectangle(
        bldg_x, SHAFT_TOP - 30, bldg_w, SHAFT_H + 30,
        fill="#d4cfc7", stroke="#999", stroke_width=1.5, rx=3,
    ))

    # building drawing
    for f in range(num_floors):
        fy = _floor_y(f) + FLOOR_H  # bottom of this floor's zone = floor line
        # floor line
        d.append(draw.Line(
            bldg_x, fy, bldg_x + bldg_w, fy,
            stroke="#888", stroke_width=1,
        ))
        # floor number (left side)
        d.append(draw.Text(
            f"{f}F", 18,
            SHAFT_X - 40, fy - FLOOR_H / 2 + 6,
            fill="#555", font_family="sans-serif", text_anchor="middle",
        ))
        # door frame on building face (right side of shaft)
        frame_x = SHAFT_X + SHAFT_W + 8
        frame_y = fy - FLOOR_H + (FLOOR_H - CABIN_H) / 2
        d.append(draw.Rectangle(
            frame_x, frame_y, 40, CABIN_H,
            fill="none", stroke="#888", stroke_width=1, rx=2,
        ))

    # roof line
    d.append(draw.Line(
        bldg_x, SHAFT_TOP - 30, bldg_x + bldg_w, SHAFT_TOP - 30,
        stroke="#777", stroke_width=2,
    ))


    # basically you tell it what to do it at each key frame
    start_cabin_y = _cabin_cy(start_floor)
    end_cabin_y   = _cabin_cy(end_floor)

    cabin_x = SHAFT_X + CABIN_PAD
    cabin_w = SHAFT_W - 2 * CABIN_PAD

    # cabin body
    cabin = draw.Rectangle(cabin_x, start_cabin_y, cabin_w, CABIN_H,
                           fill="#b0a898", stroke="#666", stroke_width=2, rx=3)
    cabin.add_key_frame(t0, y=start_cabin_y)
    cabin.add_key_frame(t2, y=start_cabin_y)
    cabin.add_key_frame(t3, y=end_cabin_y)
    cabin.add_key_frame(t5, y=end_cabin_y)
    d.append(cabin)

    # cabin interior (slightly inset, darker)
    cab_int = draw.Rectangle(cabin_x + 4, start_cabin_y + 4, cabin_w - 8, CABIN_H - 8,
                             fill="#8a7e70", stroke="none", rx=2)
    cab_int.add_key_frame(t0, y=start_cabin_y + 4)
    cab_int.add_key_frame(t2, y=start_cabin_y + 4)
    cab_int.add_key_frame(t3, y=end_cabin_y + 4)
    cab_int.add_key_frame(t5, y=end_cabin_y + 4)
    d.append(cab_int)

    # doors
    door_y_start = start_cabin_y + 6
    door_y_end   = end_cabin_y + 6
    door_h       = CABIN_H - 12

    door_left_closed_x  = cabin_x + 6
    door_right_closed_x = cabin_x + 6 + DOOR_W - 6
    door_open_offset    = DOOR_W - 10  # how far doors slide open

    # Left door
    door_l = draw.Rectangle(door_left_closed_x, door_y_start, DOOR_W - 6, door_h,
                            fill="#9e9588", stroke="#777", stroke_width=1, rx=1)
    # t0: open at start floor
    #t1: closing 
    #t2: closed, travel
    #t3: at dest, opening 
    #t4: open
    # compared to the last example, we can add keyframes using the drawsvg lib
    #vs manually adding them into the element.
    door_l.add_key_frame(t0, x=door_left_closed_x - door_open_offset,
                         y=door_y_start)
    door_l.add_key_frame(t1, x=door_left_closed_x - door_open_offset,
                         y=door_y_start)
    door_l.add_key_frame(t2, x=door_left_closed_x,
                         y=door_y_start)
    door_l.add_key_frame(t3, x=door_left_closed_x,
                         y=door_y_end)
    door_l.add_key_frame(t4, x=door_left_closed_x - door_open_offset,
                         y=door_y_end)
    door_l.add_key_frame(t5, x=door_left_closed_x - door_open_offset,
                         y=door_y_end)
    d.append(door_l)

    # Right door
    door_r = draw.Rectangle(door_right_closed_x, door_y_start, DOOR_W - 6, door_h,
                            fill="#9e9588", stroke="#777", stroke_width=1, rx=1)
    door_r.add_key_frame(t0, x=door_right_closed_x + door_open_offset,
                         y=door_y_start)
    door_r.add_key_frame(t1, x=door_right_closed_x + door_open_offset,
                         y=door_y_start)
    door_r.add_key_frame(t2, x=door_right_closed_x,
                         y=door_y_start)
    door_r.add_key_frame(t3, x=door_right_closed_x,
                         y=door_y_end)
    door_r.add_key_frame(t4, x=door_right_closed_x + door_open_offset,
                         y=door_y_end)
    door_r.add_key_frame(t5, x=door_right_closed_x + door_open_offset,
                         y=door_y_end)
    d.append(door_r)

    ind_x, ind_y = 440, 80
    ind_w, ind_h = 100, 120

    # panel
    d.append(draw.Rectangle(ind_x, ind_y, ind_w, ind_h,
                            fill="#1a1a1a", stroke="#555", stroke_width=2, rx=6))
    d.append(draw.Text("FLOOR", 10, ind_x + ind_w / 2, ind_y + 18,
                       fill="#888", text_anchor="middle", font_family="sans-serif"))

    # direction arrow
    arrow_char = "▲" if end_floor > start_floor else "▼"
    arrow_col_moving = "#ff4444" if end_floor < start_floor else "#44ff44"

    arrow = draw.Text(arrow_char, 22, ind_x + ind_w / 2, ind_y + 42,
                      fill="#333", text_anchor="middle", font_family="sans-serif")
    arrow.add_key_frame(t0, fill="#333333")
    arrow.add_key_frame(t2, fill=arrow_col_moving)
    arrow.add_key_frame(t3, fill="#333333")
    arrow.add_key_frame(t5, fill="#333333")
    d.append(arrow)

    # floor ui
    if end_floor > start_floor:
        floor_seq = list(range(start_floor, end_floor + 1))
    else:
        floor_seq = list(range(start_floor, end_floor - 1, -1))

    # Time each floor change
    floor_times = []
    floor_labels = []
    # At start
    floor_times.append(t0)
    floor_labels.append(str(start_floor))
    # during travel change at each floor crossing
    #  arrival key frame - (percent travelled the full path) * (arrival key frame - travling key frame)
    # "How far we are from arrival"
    # floor 3 is 0.25 away from floor 4 during the 1-4 path. so at that time 
    # we set the floor number to 3.
    # crude way as we dont have a model holding floor numbers
    for i, f in enumerate(floor_seq):
        if i == 0:
            continue
        frac = i / len(floor_seq)
        ft = t2 + frac * (t3 - t2)
        floor_times.append(ft)
        floor_labels.append(str(f))

    draw.native_animation.animate_text_sequence(
        d, floor_times, floor_labels,
        44, ind_x + ind_w / 2, ind_y + 88,
        fill="#00cc66", text_anchor="middle", font_family="monospace",
        font_weight="bold",
    )

    for f in range(num_floors):
        fy = _floor_y(f) + FLOOR_H / 2
        light_x = SHAFT_X - 18

        light = draw.Circle(light_x, fy, 5, fill="#333", stroke="#555", stroke_width=1)

        # Light up when cabin is at this floor
        if f == start_floor:
            light.add_key_frame(t0, fill="#00cc66")
            light.add_key_frame(t2, fill="#00cc66")
            light.add_key_frame(t2 + 0.01, fill="#333333")
            light.add_key_frame(t5, fill="#333333")
        elif f == end_floor:
            light.add_key_frame(t0, fill="#333333")
            light.add_key_frame(t3 - 0.01, fill="#333333")
            light.add_key_frame(t3, fill="#00cc66")
            light.add_key_frame(t5, fill="#00cc66")
        d.append(light)

    # status
    status_times = [t0, t1, t2, t3, t4]
    status_texts = ["Doors open", "Closing...", "Traveling", "Arriving", "Doors open"]
    draw.native_animation.animate_text_sequence(
        d, status_times, status_texts,
        12, ind_x + ind_w / 2, ind_y + ind_h + 20,
        fill="#666", text_anchor="middle", font_family="sans-serif",
    )

    return d