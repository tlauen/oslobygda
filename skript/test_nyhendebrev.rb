require "minitest/autorun"
require "tempfile"
require_relative "send_nyhendebrev_brevo"

class NewsletterTests < Minitest::Test
  def test_escaped_event_text
    item=render_event_item({"dato"=>Date.new(2026,11,18),"start"=>"21:00","tittel"=>"<script>bad</script> & dans","stad"=>"<b>Oslo</b>"})
    assert_includes item,"&lt;script&gt;"
    refute_includes item,"<script>"
    assert_includes item,"&lt;b&gt;Oslo&lt;/b&gt;"
  end
  def test_cancelled_events_are_not_announced
    Tempfile.create(["events", ".yml"]) do |f|
      f.write([{ "uid"=>"pobb-test", "dato"=>"2026-11-18", "avlyst"=>true},{"uid"=>"pobb-active", "dato"=>"2026-12-01"}].to_yaml)
      f.flush
      assert_equal ["pobb-active"],load_events(f.path).map { |e| e["uid"] }
    end
  end
end
