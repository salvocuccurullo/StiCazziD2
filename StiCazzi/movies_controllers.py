"""
 Django2 Movies Controller
"""

import json
import decimal
import time
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.db.models import Q, F, Count, Avg, CharField
from django.db.models.functions import Cast
from django.forms.models import model_to_dict

from StiCazzi.models import Movie, TvShow, User, TvShowVote, Notification, Catalogue, Like
from StiCazzi.controllers import check_session, test_session
from StiCazzi.covers_controllers import upload_cover
from StiCazzi.utils import safe_file_name
logger = logging.getLogger(__name__)

def get_tvshows_new_opt(request):
    """ Get Tvshow New """
    logger.debug("Get Tvshows new opt called")
    response = {'result': 'success'}

    try:
        i_data = json.loads(request.body)
        username = i_data.get('username', '')
        firebase_id_token = i_data.get('firebase_id_token', '')
        kanazzi = i_data.get('kanazzi', '')
        query = i_data.get('query', '')
        limit = i_data.get('limit', 15)
        current_page = i_data.get('current_page', 1)
        lazy_load = i_data.get('lazy_load', True)
    except (TypeError, ValueError):
        response['result'] = 'failure'
        response['message'] = 'Bad input format'
        return JsonResponse(response, status=400)

    if not check_session(kanazzi, username, action='gettvshows3', store=True):
        response['result'] = 'failure'
        response['message'] = 'Invalid Session'
        return JsonResponse(response, status=401)

    #logger.debug("Current page: %s", current_page)

    if query and len(query) < 4:
        if int(current_page) == 1:
            logger.debug("Query too short: %s", query)
            response['result'] = 'failure'
            response['message'] = 'Query String too short'
            return JsonResponse(response, status=404)
        else:
            query = ''

    out_list = []
    movie_list = TvShow.objects.filter(
        Q(title__icontains=query) | Q(media__icontains=query)
    ).order_by('-created')

    lower_bound = limit * (current_page - 1)
    upper_bound = current_page * limit

    if lazy_load:
        bounded = movie_list[lower_bound: upper_bound]
    else:
        bounded = movie_list

    # Adding all NW
    if not query and current_page == 1:
        nwtv = TvShowVote.objects.filter(now_watching=True)
        nwtv_list = [show.tvshow for show in nwtv if show.tvshow not in bounded]
        nwtv_list = list(set(nwtv_list))
        bounded = list(bounded) + nwtv_list
    # End Adding all NW

    for tvs in bounded:
        # dt = tvs.created.strftime("%A, %d. %B %Y %I:%M%p")
        movie_created = tvs.created.strftime("%d %B %Y ")
        dtsec = time.mktime(tvs.created.timetuple())

        tvshow_votes = TvShowVote.objects.filter(tvshow=tvs)
        avg_vote = tvshow_votes.filter(now_watching=0).aggregate(avg_vote=Avg("vote"))['avg_vote']
        if avg_vote:
            avg_vote_str = "%.2f" % avg_vote
        else:
            avg_vote_str = "0.0"

        dragon = tvshow_votes.values('id_vote','episode', 'season', 'comment', 'now_watching')\
                             .annotate(us_id_vote=F('id_vote'))\
                             .annotate(us_username=F('user__username'))\
                             .annotate(us_name=F('user__name'))\
                             .annotate(us_vote=Cast('vote', CharField()))\
                             .annotate(us_date=Cast('created', CharField()))\
                             .annotate(us_update=Cast('updated', CharField()))

        u_v_dict = {}
        for rec in list(dragon):
            u_v_dict[rec['us_username']] = rec

        tvshow_dict = {'title': tvs.title,
                       'media': tvs.media,
                       # 'vote': str_vote1,
                       'username': tvs.user.username,
                       'name': tvs.user.name,
                       'poster': tvs.poster,
                       'datetime_sec': dtsec,
                       'u_v_dict': u_v_dict,
                       'type': tvs.type,
                       'tvshow_type': tvs.tvshow_type,
                       'director': tvs.director,
                       'year': tvs.year,
                       'id': tvs.id_tv_show,
                       'link': tvs.link,
                       'datetime': movie_created,
                       'avg_vote': avg_vote_str,
                       'serie_season': tvs.serie_season,
                       'miniseries': tvs.miniseries
                      }
        out_list.append(tvshow_dict)

    has_more = True
    if len(movie_list) <= upper_bound:
        has_more = False
    if not lazy_load:
        has_more = False

    #logger.debug("List size: %s", str(len(bounded)))
    #logger.debug("Has more: %s", str(has_more))
    #logger.debug("Query: %s", query)
    #logger.debug("Lower bound: %s", str(lower_bound))
    #logger.debug("Upper bound: %s", str(upper_bound))

    tvshow_stat = dict(\
                  TvShow.objects\
                      .filter(
                          Q(title__icontains=query) | Q(media__icontains=query)
                      )\
                      .values("tvshow_type")\
                      .annotate(count=Count('tvshow_type'))\
                      .values_list("tvshow_type", "count")
                  )
    tvshow_stat = {'movie': tvshow_stat.get('movie', 0), 'serie': tvshow_stat.get('serie', 0)}

    votes_user = TvShowVote.objects.annotate(name=F('user__username'))\
                 .values("name")\
                 .annotate(count=Count('user'))\
                 .order_by('-count')
    votes_user = [{"name": rec['name'], "count": rec['count']} for rec in list(votes_user)]

    response['payload'] = {'stat': tvshow_stat,
                           'tvshows': out_list,
                           'query': query,
                           'has_more': has_more,
                           'votes_user': votes_user,
                           'total_show': movie_list.count()
                          }

    return JsonResponse(response)


def get_movies_ct(request):
    """ Get Tvshow CT """

    movie_list = Movie.objects.all().exclude(cinema="")
    logger.debug("Movie CT (unsecure) called")
    out = []
    for rec in movie_list:
        movie_dict = {'id': rec.id_movie,
                      'title': rec.title,
                      'year': rec.year,
                      'cinema': rec.cinema,
                      'cast': rec.cast,
                      'director': rec.director,
                      'filmtv': rec.filmtv
                     }
        out.append(movie_dict)

    response = {}
    response['result'] = 'success'
    response['payload'] = out

    return JsonResponse(response)


@ensure_csrf_cookie
def setlike(request):
    """ Set Like """

    logger.debug("Like called")
    response_data = {}
    response_data['result'] = 'success'
    try:
        i_data = json.loads(request.body)
        username = i_data.get('username', '')
        kanazzi = i_data.get('kanazzi', '')
        id_vote = i_data.get('id_vote', '')
        reaction = i_data.get('reaction', '')
        action = i_data.get('action','fetch')
    except (TypeError, ValueError):
        response_data['result'] = 'failure'
        response_data['message'] = 'Bad input format'
        return JsonResponse(response_data, status=400)

    if not check_session(kanazzi, username, action='setlike', store=True):
        response_data['result'] = 'failure'
        response_data['message'] = 'Invalid Session'
        return JsonResponse(response_data, status=401)

    current_user = User.objects.filter(username=username).first()

    if action == "set":

      items = Like.objects.filter(id_vote=id_vote, user=current_user)
      vote = TvShowVote.objects.filter(id_vote=id_vote).first()
      tvshow = TvShow.objects.filter(id_tv_show=vote.tvshow_id).first()
      if items:
          like = items.first()
          if reaction == "O":
            like.delete()
          else:
            like.reaction = reaction
            like.save()
          response_data['message'] = 'Like updated for id_vote %s' % id_vote
      else:
          like = Like(id_vote=vote, reaction=reaction, user=current_user)
          like.save()
          response_data['message'] = 'Like created for id_vote %s' % id_vote

      # Special usage for notification
      # title -> tv_show_id
      # message -> the guy who has wrote the comment
      # username -> the guy who has clicked on like
      if reaction != "O" and current_user.username != vote.user.username:
        notification = Notification(
                type="like", \
                title="%s" % tvshow.id_tv_show, \
                message="%s" % vote.user.username, \
                username=current_user.username)
        notification.save()

    response_data['payload'] = {'id_vote': id_vote, 'count': len(Like.objects.filter(id_vote=id_vote, reaction="*")), 'you': len(Like.objects.filter(id_vote=id_vote, reaction="*", user=current_user))}
 
    return JsonResponse(response_data)


@ensure_csrf_cookie
def deletemovie(request):
    """ Delete Tvshow """

    response_data = {}
    response_data['result'] = 'success'

    # backward compatibility
    movie_id = request.POST.get('id', '')
    username = request.POST.get('username', '')
    kanazzi = request.POST.get('kanazzi', '')
    # end backward compatibility

    if not username:
        try:
            i_data = json.loads(request.body)
            username = i_data.get('username', '')
            kanazzi = i_data.get('kanazzi', '')
            movie_id = i_data.get('id', '')
        except (TypeError, ValueError):
            response['result'] = 'failure'
            response['message'] = 'Bad input format'
            return JsonResponse(response, status=400)


    if not check_session(kanazzi, username, action='deletemovie', store=True):
        response_data['result'] = 'failure'
        response_data['message'] = 'Invalid Session'
        return JsonResponse(response_data, status=401)

    current_user = User.objects.filter(username=username)
    # Check existing votes
    tvrs = TvShowVote.objects.filter(tvshow=movie_id).exclude(user=current_user[0])

    if tvrs:
        vote_check = tvrs[0]
        response_data['message'] = 'Cannot delete %s. It has been voted by other users!' % (vote_check.tvshow.title)
        response_data['result'] = 'failure'
    else:
        show_to_delete = TvShow.objects.filter(id_tv_show=movie_id)
        if show_to_delete:
            tvshow = show_to_delete[0]
            tvshow.delete()
            response_data['message'] = 'Tvshow with id=' + movie_id + " deleted succcessfully."
        else:
            response_data['result'] = 'failure'
            response_data['message'] = 'Cannot delete tvshow with id=' + movie_id + ". It does not exist!"

    return JsonResponse(response_data)


def create_update_vote(current_user, tvshow, vote_dict):
    """ Create Update vote """
    tvsv = TvShowVote.objects.filter(user=current_user, tvshow=tvshow[0])
    if not tvsv:
        tvsv = TvShowVote(vote=vote_dict['vote'], user=current_user, tvshow=tvshow[0], \
                          now_watching=vote_dict["nw"], season=vote_dict["season"], \
                          episode=vote_dict["episode"], comment=vote_dict['comment'])
        tvsv.save()

        if vote_dict.get('like',''):
            like = Like(reaction=vote_dict['like'], user=current_user, id_vote=tvsv)
            like.save()

        if not vote_dict["nw"]:
            notification = Notification(
                type="new_vote", \
                title="%s voted for a %s..." % (current_user.username, tvshow[0].tvshow_type), \
                message="Title: %s - Vote: %s " \
                % (tvshow[0].title, vote_dict["vote"]), username=current_user.username)
            notification.save()
    else:
        current_vote = tvsv[0]
        if vote_dict['giveup']:
            current_vote.delete()

            notification = Notification(
                type="give_up", \
                title="%s gave up to follow a %s" % (current_user.username, tvshow[0].tvshow_type), \
                message="%s" % tvshow[0].title, username=current_user.username)
            notification.save()

        else:

            finished = False
            first_comment = False

            if current_vote.now_watching and not vote_dict["nw"]:
                finished = True

            if current_vote.comment == "" and vote_dict["comment"] != "":
                first_comment = True

            current_vote.vote = vote_dict['vote']
            current_vote.now_watching = vote_dict["nw"]
            current_vote.episode = vote_dict["episode"]
            current_vote.season = vote_dict["season"]
            current_vote.comment = vote_dict["comment"]
            current_vote.save()

            if vote_dict.get('like',''):
                like = Like(reaction=vote_dict['like'], user=current_user, id_vote=current_vote)
                like.save()

            if vote_dict.get('like',''):
                like = Like(reaction=vote_dict['like'], user=current_user)
                like.save()

            if finished:
                notification = Notification(
                    type="new_vote", \
                    title="%s voted for a %s..." % (current_user.username, tvshow[0].tvshow_type), \
                    message="Title: %s - Vote: %s " \
                    % (tvshow[0].title, vote_dict["vote"]), username=current_user.username)
                notification.save()

            if first_comment:
                notification = Notification(
                    type="new_comment", \
                    title="%s commented %s..." % (current_user.username, tvshow[0].tvshow_type), \
                    message="Title: %s - %s... " \
                    % (tvshow[0].title, vote_dict["comment"][:30]), username=current_user.username)
                notification.save()

    # logger.debug(vote_dict)
    if vote_dict["nw"] and str(vote_dict["episode"]) == "1":
        notification = Notification(
            type="new_nw", \
            title="%s started to watch a %s..." % (current_user.username, tvshow[0].tvshow_type), \
            message="Title: %s - S%s E%s " \
            % (tvshow[0].title, tvshow[0].serie_season, vote_dict["episode"]), username=current_user.username)
        notification.save()


@ensure_csrf_cookie
def savemovienew(request):
    """ Save Movie New """

    response_data = {}
    response_data['result'] = 'success'

    id_movie = request.POST.get('id', '')
    title = request.POST.get('title', '')
    media = request.POST.get('media', '')
    link = request.POST.get('link', '')
    vote = request.POST.get('vote', '')
    type = request.POST.get('type', 'brand_new')
    tvshow_type = request.POST.get('tvshow_type', 'movie')
    serie_season = request.POST.get('serie_season', 1)
    miniseries_sw = request.POST.get('miniseries', False)
    clone_season = request.POST.get('clone_season', 1)
    director = request.POST.get('director', '')
    year = request.POST.get('year', '')
    username = request.POST.get('username', '')
    kanazzi = request.POST.get('kanazzi', '')
    now_watch_sw = request.POST.get('nw', False)
    giveup_sw = request.POST.get('giveup', False)
    later_sw = request.POST.get('later', False)
    season = request.POST.get('season', 1)
    episode = request.POST.get('episode', 1)
    comment = request.POST.get('comment', '')
    like = request.POST.get('like', '')
    uploaded_file = request.FILES.get('pic', '')
    poster_name = ''
    upload_file_res = {}

    logger.debug(id_movie)
    # logger.debug (title)
    # logger.debug (media)
    # logger.debug (type)

    if uploaded_file:
        logger.debug("A file has been uploaded... %s", uploaded_file.name)
        temp_f_name = title + '_' + uploaded_file.name
        poster_name = safe_file_name(temp_f_name, uploaded_file.content_type)

    now_watch = False
    if now_watch_sw == "on":
        now_watch = True

    giveup = False
    if giveup_sw == "on":
        giveup = True

    later = False
    if later_sw == "on":
        later = True

    miniseries = False
    if miniseries_sw == "on":
        miniseries = True

    if not check_session(kanazzi, username, action='savemovienew', store=True):
        response_data['result'] = 'failure'
        response_data['message'] = 'Invalid Session'
        return JsonResponse(response_data, status=401)

    if not title or not media or not tvshow_type:
        response_data['result'] = 'failure'
        response_data['message'] = 'Missing required data: check title, media and type'
        return JsonResponse(response_data)

    current_tvshow = TvShow.objects.filter(id_tv_show=id_movie)
    current_user = User.objects.filter(username=username)[0]

    # Movie exists and the current user is not the owner
    if current_tvshow and username != current_tvshow[0].user.username:
        logger.debug("User not owner of the movie is voting...")
        data_vote = {'nw': now_watch,
                     'episode': episode,
                     'season': season,
                     'vote': vote,
                     'giveup': giveup,
                     'comment': comment,
                     'like': like
                    }

        tvshow = current_tvshow[0]

        if not later:
            create_update_vote(current_user, current_tvshow, data_vote)

        # New feature: to allow not movie owner to upload the poster, set a link and set the season
        # 2020-03-21 added type and media

        tvshow.media = media
        tvshow.tvshow_type = tvshow_type
        tvshow.serie_season = serie_season
        tvshow.miniseries = miniseries
        tvshow.save()

        if uploaded_file:
            upload_file_res = upload_cover(request, poster_name)

        upload_res = upload_file_res.get('result', 'failure')
        if upload_res == 'failure':
            poster_name = ''
        else:
            tvshow.poster = poster_name

        if link:
            tvshow.link = link

        if upload_res != 'failure' or (tvshow.link == "" and link):
            tvshow.save()

            notification = Notification(
                type="new_movie", \
                title="%s uploaded a new poster/link" \
                % username, message="Title: %s" % title, username=username)
            notification.save()

        # End New feature

    else:
        if not current_tvshow:  # Movie does not exist

            if uploaded_file:
                upload_file_res = upload_cover(request, poster_name)

            upload_res = upload_file_res.get('result', 'failure')
            if upload_res == 'failure':
                poster_name = ''

            logger.debug("Adding tvshow... Title: %s", title)

            tvshow = TvShow(title=title, media=media, link=link, vote=vote, user=current_user,
                            type=type, tvshow_type=tvshow_type,
                            director=director, year=year,
                            poster=poster_name, serie_season=serie_season, miniseries=miniseries)
            tvshow.save()

            if tvshow_type == 'serie' and int(clone_season) > 1 and int(clone_season) < 10:
                logger.debug("Cloning serie %s started..." % tvshow.title)
                start = int(tvshow.serie_season) + 1
                stop = start + int(clone_season)
                for i in range(start, stop):
                    tvshow_clone = TvShow(title=title, media=media, link=link, vote=vote, user=current_user,
                            type=type, tvshow_type=tvshow_type,
                            director=director, year=year, miniseries=miniseries,
                            poster='', serie_season=i)
                    logger.debug("Saving season %s" % str(tvshow_clone.serie_season))
                    tvshow_clone.save()
                logger.debug("Cloning serie %s finished." % tvshow_clone.title)

            if not later:

                if not episode:
                    episode = 1

                if not season:
                    season = 1

                tvsv = TvShowVote(
                    vote=vote,
                    user=current_user,
                    tvshow=tvshow,
                    now_watching=now_watch,
                    season=season,
                    episode=episode,
                    comment=comment
                )
                tvsv.save()

            # Workaround to be removed
            show_type_string = tvshow_type
            if show_type_string == "serie":
              show_type_string = "series"
            ###########################

            notification = Notification(
                type="new_movie", \
                title="%s added a new %s" % (username, show_type_string), \
                message="Title: %s" % title, username=username)
            notification.save()

            response_data['message'] = 'TvShow/Movie %s saved!' % title

        else:  # Movie exists and the owner is modifyng it

            if uploaded_file:
                upload_file_res = upload_cover(request, poster_name)

            upload_res = upload_file_res.get('result', 'failure')
            if upload_res == 'failure':
                poster_name = ''
            else:
                notification = Notification(
                    type="new_movie", \
                    title="%s added a new poster" % username, \
                    message="Title: %s" % title, username=username)
                notification.save()

            logger.debug("Updating tvshow... Title: %s", title)
            tvshow = current_tvshow[0]
            tvshow.title = title
            tvshow.media = media
            tvshow.link = link
            tvshow.vote = vote
            tvshow.type = type
            tvshow.serie_season = serie_season
            tvshow.tvshow_type = tvshow_type
            tvshow.miniseries = miniseries
            tvshow.director = director
            tvshow.year = year
            if poster_name:
                tvshow.poster = poster_name
            tvshow.save()

            data_vote = {'nw': now_watch,
                         'episode': episode,
                         'season': season,
                         'vote': vote,
                         'giveup': giveup,
                         'comment': comment
                        }
            if not later:
                create_update_vote(current_user, current_tvshow, data_vote)

    response_data.update({"upload_result": upload_file_res})

    return JsonResponse(response_data)


def get_movies_datatable(request):
    """ Get Tvshow for js datatable """
    movies_list = Movie.objects.all().exclude(cinema="")
    out = []
    for rec in movies_list:
        movie_dict = {
            '0': rec.title,
            '1': rec.year,
            '2': rec.cinema,
            '3': rec.cast,
            '4': rec.director,
            '5': rec.filmtv
        }
        out.append(movie_dict)

    response_data = {}
    response_data['result'] = 'success'
    response_data['data'] = out

    return JsonResponse(response_data)


def get_catalogue(request):
    """ Get Media Catalogue """
    response = {'result':'success'}

    try:
        i_data = json.loads(request.body)
        username = i_data.get('username', '')
        firebase_id_token = i_data.get('firebase_id_token', '')
        cat_type = i_data.get('cat_type', '')
        kanazzi = i_data.get('kanazzi', '')
    except (TypeError, ValueError):
        response['result'] = 'failure'
        response['message'] = 'Bad input format'
        return JsonResponse(response, status=400)

    if not check_session(kanazzi, username, action='get_catalogue', store=True):
        response['result'] = 'failure'
        response['message'] = 'Invalid Session'
        return JsonResponse(response, status=401)

    if not cat_type:
        media_cat = Catalogue.objects.all()
    else:
        media_cat = Catalogue.objects.filter(cat_type=cat_type).order_by('label')

    response['payload'] = [model_to_dict(rec) for rec in media_cat]

    return JsonResponse(response)
