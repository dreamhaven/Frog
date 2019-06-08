##################################################################################################
# Copyright (c) 2012 Brett Dixon
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in 
# the Software without restriction, including without limitation the rights to use,
# copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the 
# Software, and to permit persons to whom the Software is furnished to do so, 
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all 
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR 
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS 
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR 
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER 
# IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION 
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
##################################################################################################

import datetime

from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse, HttpResponseForbidden
from django.utils import timezone

from frog import models
from frog.common import Result, getHashForFile, cropCenter, saveAsPng

from path import path as Path


class MediaTypeError(Exception):
    pass


@csrf_exempt
def upload(request):
    res = Result()

    uploadfile = request.FILES.get('file')

    if uploadfile:
        filename = uploadfile.name

        path = request.POST.get('path', None)
        if path:
            foreignPath = path.replace("'", "\"")
        else:
            foreignPath = filename

        galleries = request.POST.get('galleries', '1').split(',')
        tags = [_.strip() for _ in request.POST.get('tags', '').split(',') if _]
        title = request.POST.get('title')
        description = request.POST.get('description', '')
        force = request.POST.get('force')

        try:
            username = request.POST.get('user', False)
            if username:
                user = User.objects.get(username=username)
            else:
                user = request.user
            
            uniqueName = request.POST.get('uid', models.Piece.getUniqueID(foreignPath, user))

            if galleries and models.Gallery.objects.filter(pk__in=[int(g) for g in galleries], uploads=False):
                raise PermissionDenied()

            extension = Path(filename).ext.lower()
            if extension in models.FILE_TYPES['image']:
                model = models.Image
            elif extension in models.FILE_TYPES['video']:
                model = models.Video
            elif extension in models.FILE_TYPES['marmoset']:
                model = models.Marmoset
            else:
                raise MediaTypeError('{} is not a supported file type'.format(extension))

            obj, created = model.objects.get_or_create(unique_id=uniqueName, defaults={'author': user, 'hidden': False})
            guid = obj.getGuid()
            hashVal = getHashForFile(uploadfile)

            if hashVal == obj.hash and not force:
                for gal in galleries:
                    g = models.Gallery.objects.get(pk=int(gal))
                    obj.gallery_set.add(g)
                res.append(obj.json())
                res.message = "Files were the same"
                res.append(obj.json())

                return JsonResponse(res.asDict())

            objPath = models.ROOT
            if models.FROG_PATH:
                objPath = objPath / models.FROG_PATH
            objPath = objPath / guid.guid[-2:] / guid.guid / filename
            
            hashPath = objPath.parent / hashVal + objPath.ext
            
            if not objPath.parent.exists():
                objPath.parent.makedirs()

            # Save uploaded files to asset folder
            for key, uploadfile in request.FILES.items():
                if key == 'file':
                    handle_uploaded_file(hashPath, uploadfile)
                else:
                    dest = objPath.parent / uploadfile.name
                    handle_uploaded_file(dest, uploadfile)

                    if key == 'thumbnail':
                        thumbnail = saveAsPng(dest)
                        cropped = cropCenter(models.pilImage.open(thumbnail), models.FROG_THUMB_SIZE, models.FROG_THUMB_SIZE)
                        cropped.save(thumbnail)
                        obj.custom_thumbnail = obj.getPath(True) / thumbnail.name
                        obj.save()

            obj.hash = hashVal
            obj.foreign_path = foreignPath
            obj.title = title or objPath.namebase
            obj.description = description
            obj.export(hashVal, hashPath, tags=tags, galleries=galleries)

            res.append(obj.json())

        except MediaTypeError as err:
            res.isError = True
            res.message = str(err)
            
            return JsonResponse(res.asDict())

    else:
        res.isError = True
        res.message = "No file found"

    return JsonResponse(res.asDict())


def handle_uploaded_file(dest, f):
    if not dest.parent.exists():
        dest.parent.makedirs()

    destination = open(dest, 'wb+')
    for chunk in f.chunks():
        destination.write(chunk)
    destination.close()

    return True
