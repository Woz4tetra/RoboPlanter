import os
import sys
import cv2
import time


def generate_video(image_paths, image_width, image_height, output_dir, fps):
    video = cv2.VideoWriter(os.path.join(output_dir, "video.avi"), cv2.VideoWriter_fourcc(*"MJPG"), fps, (image_width, image_height))

    prev_time = time.time()
    for index, path in enumerate(image_paths):
        print(path)
        if time.time() - prev_time > 1.0:
            print("%0.1f%%" % (index / len(image_paths) * 100.0))
            prev_time = time.time()
        image = cv2.imread(path)
        if image is None:
            raise FileNotFoundError(path)

        # timestamp = timestamps[index]
        # filename = "%s.png" % timestamp
        # cv2.imwrite(os.path.join(output_dir, "images", filename), image)

        video.write(image)

        # cv2.imshow("image", image)
        # key = cv2.waitKey(1)
        # if 0 < key < 0x100 and chr(key) == 'q':
        #     break
    video.release()
    cv2.destroyAllWindows()


def get_path_index(path):
    # example: "img0-2020-10-18T23-38-19--433983.jpg"
    dash_index = path.find("-")
    return int(path[len("img"):dash_index])


def main():
    in_dir = "."
    out_dir = "."

    if len(sys.argv) > 1:
        try:
            in_dir = sys.argv[1]
        except ValueError:
            pass

    if len(sys.argv) > 2:
        try:
            out_dir = sys.argv[2]
        except ValueError:
            pass

    paths = list(os.listdir(in_dir))
    paths.sort(key=lambda x: get_path_index(x))
    for index, path in enumerate(paths):
        paths[index] = os.path.join(in_dir, path)

    generate_video(paths, 2208, 1712, out_dir, 30)

main()
