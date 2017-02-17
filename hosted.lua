--[[

  Part of info-beamer hosted. You can find the latest version
  of this file at:
  
  https://github.com/info-beamer/package-sdk

  Copyright (c) 2014,2015,2016,2017 Florian Wesch <fw@dividuum.de>
  All rights reserved.

  Redistribution and use in source and binary forms, with or without
  modification, are permitted provided that the following conditions are
  met:

      Redistributions of source code must retain the above copyright
      notice, this list of conditions and the following disclaimer. 

      Redistributions in binary form must reproduce the above copyright
      notice, this list of conditions and the following disclaimer in the
      documentation and/or other materials provided with the
      distribution.  

  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS
  IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
  THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
  PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
  CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
  EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
  PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
  PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
  LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
  NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
  SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

]]--

local resource_types = {
    ["image"] = function(value)
        local surface
        local image = {
            asset_name = value.asset_name,
            filename = value.filename,
            type = value.type,
        }

        function image.ensure_loaded()
            if not surface then
                surface = resource.load_image(value.asset_name)
            end
            return surface
        end
        function image.load()
            image.ensure_loaded()
            local state = surface:state()
            return state ~= "loading"
        end
        function image.get_surface()
            return image.ensure_loaded()
        end
        function image.draw(...)
            image.ensure_loaded():draw(...)
        end
        function image.unload()
            if surface then
                surface:dispose()
                surface = nil
            end
        end
        function image.get_config()
            return image
        end
        return image
    end;
    ["video"] = function(value)
        local surface
        local video = {
            asset_name = value.asset_name,
            filename = value.filename,
            type = value.type,
        }
        function video.ensure_loaded(opt)
            if not surface then
                surface = util.videoplayer(value.asset_name, opt)
            end
            return surface
        end
        function video.load(opt)
            video.ensure_loaded(opt)
            local state = surface:state()
            return state ~= "loading"
        end
        function video.get_surface(opt)
            return video.ensure_loaded(opt)
        end
        function video.draw(...)
            video.ensure_loaded():draw(...)
        end
        function video.unload()
            if surface then
                surface:dispose()
                surface = nil
            end
        end
        function video.get_config()
            return video
        end
        return video
    end;
    ["child"] = function(value)
        local surface
        local child = {
            asset_name = value.asset_name,
            filename = value.filename,
            type = value.type,
        }
        function child.ensure_loaded()
            if surface then
                surface:dispose()
            end
            surface = resource.render_child(value.asset_name)
            return surface
        end
        function child.load()
            return true
        end
        function child.get_surface()
            return child.ensure_loaded()
        end
        function child.draw(...)
            child.ensure_loaded():draw(...)
        end
        function child.unload()
            if surface then
                surface:dispose()
                surface = nil
            end
        end
        function child.get_config()
            return child
        end
        return child
    end;
    ["json"] = function(value)
        return require("json").decode(value)
    end;
}

local types = {
    ["text"] = function(value)
        return value
    end;
    ["string"] = function(value)
        return value
    end;
    ["integer"] = function(value)
        return value
    end;
    ["select"] = function(value)
        return value
    end;
    ["device"] = function(value)
        return value
    end;
    ["boolean"] = function(value)
        return value
    end;
    ["duration"] = function(value)
        return value
    end;
    ["custom"] = function(value)
        return value
    end;
    ["color"] = function(value)
        local color = {}
        color.r = value.r
        color.g = value.g
        color.b = value.b
        color.a = value.a
        color.rgba_table = {color.r, color.g, color.b, color.a}
        color.rgba = function()
            return color.r, color.g, color.b, color.a
        end
        color.rgb_with_a = function(a)
            return color.r, color.g, color.b, a
        end
        color.clear = function()
            gl.clear(color.r, color.g, color.b, color.a)
        end
        return color
    end;
    ["resource"] = function(value)
        return resource_types[value.type](value)
    end;
    ["font"] = function(value)
        return resource.load_font(value.asset_name)
    end;
}

local function parse_config(options, config)
    local function parse_recursive(options, config, target)
        for _, option in ipairs(options) do
            local name = option.name
            if name then
                if option.type == "list" then
                    local list = {}
                    for _, child_config in ipairs(config[name]) do
                        local child = {}
                        parse_recursive(option.items, child_config, child)
                        list[#list + 1] = child
                    end
                    target[name] = list
                else
                    target[name] = types[option.type](config[name])
                end
            end
        end
    end
    local current_config = {}
    parse_recursive(options, config, current_config)
    return current_config
end

return {
    parse_config = parse_config;
}
