# -*- mode: ruby -*-
Vagrant.configure(2) do |config|
  config.vm.box = "chef/centos-6.5"
  config.vm.network :forwarded_port, guest: 5000, host: 5000
  config.vm.provision :shell, :path => "vagrant-provision.sh"
end
