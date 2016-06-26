/* Project specific Javascript goes here. */
$( document ).ready(function() {
});

$('#songModal').on('show.bs.modal', function(event) {
  var button = $(event.relatedTarget);
  var songId = button.data('songId');
  var chartSlug = button.data('chart-slug');
  var modal = $(this);

  var url = '/api/v1/songs/' + songId + '/?format=json';

  $.getJSON(url, function(data) {
    var artistNames = [];

    data['artists'].forEach(function(artist) {
      artistNames.push(artist['name']);
    });

    var currentRank = 'Unranked';
    var peakRank = 'Unranked';

    var kchartDetails = data['chart_details']['realtime']['kchart'];
    if (kchartDetails['has_charted'] == true) {
      if (kchartDetails['current_position'])
      {
        currentRank = kchartDetails['current_position'];
      }
      peakRank = kchartDetails['peak_position'];
    }

    modal.find('#songTitle').text(data['name']);
    modal.find('#songAlbum').text(data['album']['name']);
    modal.find('#songArtists').text(artistNames.join(', '));
    modal.find('#songReleaseDate').text(data['release_date']);
    modal.find('#songRank').text(currentRank);
    modal.find('#songPeakRank').text(peakRank);
  });
});

$(function () {
  $('[data-toggle="tooltip"]').tooltip()
})
