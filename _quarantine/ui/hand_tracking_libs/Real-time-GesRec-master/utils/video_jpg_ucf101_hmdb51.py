import os
import subprocess
import sys


def class_process(dir_path, dst_dir_path, class_name):
  class_path = os.path.join(dir_path, class_name)
  if not os.path.isdir(class_path):
    return

  dst_class_path = os.path.join(dst_dir_path, class_name)
  if not os.path.exists(dst_class_path):
    os.mkdir(dst_class_path)

  for file_name in os.listdir(class_path):
    if '.avi' not in file_name:
      continue
    name, ext = os.path.splitext(file_name)
    dst_directory_path = os.path.join(dst_class_path, name)

    video_file_path = os.path.join(class_path, file_name)
    try:
      if os.path.exists(dst_directory_path):
        if not os.path.exists(os.path.join(dst_directory_path, 'image_00001.jpg')):
          subprocess.call(f'rm -r \"{dst_directory_path}\"', shell=True)
          print(f'remove {dst_directory_path}')
          os.mkdir(dst_directory_path)
        else:
          continue
      else:
        os.mkdir(dst_directory_path)
    except:
      print(dst_directory_path)
      continue
    cmd = f'ffmpeg -i \"{video_file_path}\" -vf scale=-1:240 \"{dst_directory_path}/image_%05d.jpg\"'
    print(cmd)
    subprocess.call(cmd, shell=True)
    print('\n')

if __name__=="__main__":
  dir_path = sys.argv[1]
  dst_dir_path = sys.argv[2]

  for class_name in os.listdir(dir_path):
    class_process(dir_path, dst_dir_path, class_name)
