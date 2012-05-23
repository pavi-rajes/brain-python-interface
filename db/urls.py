from django.conf.urls.defaults import *

# Uncomment the next two lines to enable the admin:
from django.contrib import admin
admin.autodiscover()

urlpatterns = patterns('',
	(r'^$', 'tracker.views.list'),
    (r'^ajax/task_info/(?P<idx>\d+)/', "tracker.ajax.task_info"),
    (r'^ajax/exp_info/(?P<idx>\d+)/', 'tracker.ajax.exp_info'),
    (r'^ajax/seq_data/(?P<idx>\d+)/', 'tracker.ajax.seq_data'),
    (r'^start/?', 'tracker.ajax.start_experiment'),
    (r'^test/?', 'tracker.ajax.start_experiment', dict(save=False)),
    (r'^stop/?', 'tracker.ajax.stop_experiment'),

    (r'^RPC2/?', 'tracker.dbq.rpc_handler'),

    (r'^report/?', 'tracker.ajax.report'),
    # Uncomment the admin/doc line below to enable admin documentation:
    (r'^admin/doc/', include('django.contrib.admindocs.urls')),
    # Uncomment the next line to enable the admin:
    (r'^admin/', include(admin.site.urls)),
)
