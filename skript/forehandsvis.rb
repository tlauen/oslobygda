#!/usr/bin/env ruby
# Lokal Jekyll-førehandsvising med automatisk ombygging og Python sin HTTP-server.
require 'tmpdir'

# Liquid-versjonen brukt av Jekyll 3 spør etter API som vart fjerna i Ruby 3.2.
# Berre for den lokale førehandsvisingsprosessen, ikkje ein del av nettsida.
unless Object.method_defined?(:tainted?)
  class Object
    def tainted?; false; end
    def taint; self; end
    def untaint; self; end
  end
end

require 'jekyll'
require 'jekyll-watch'

source = File.expand_path('..', __dir__)
port = Integer(ENV.fetch('PORT', '4000'))
Dir.mktmpdir('oslobygda-preview-') do |destination|
  config = Jekyll.configuration({
    'source' => source, 'destination' => destination,
    'disable_disk_cache' => true, 'url' => "http://localhost:#{port}",
    'host' => '127.0.0.1'
  })
  site = Jekyll::Site.new(config)
  site.process
  server = Process.spawn('python3', '-m', 'http.server', port.to_s,
                         '--bind', '127.0.0.1', '--directory', destination)
  begin
    puts "Opne http://localhost:#{port}/kalender/"
    puts 'Endringar blir bygde automatisk. Last nettlesarsida på nytt etter lagring.'
    puts 'Stopp med Ctrl+C. Ved endring av _config.yml: stopp og start på nytt.'
    $stdout.flush
    Jekyll::Watcher.watch(config, site)
  ensure
    begin
      Process.kill('TERM', server)
      Process.wait(server)
    rescue Errno::ESRCH, Errno::ECHILD
      # Serveren var allereie avslutta.
    end
  end
end
